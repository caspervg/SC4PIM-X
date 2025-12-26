#include "FSHReader.h"

#include <algorithm>
#include <string>
#include <squish/squish.h>

#include "QFSDecompressor.h"
#include "SafeSpanReader.h"

namespace {

ParseExpected<uint32_t> ReadUInt24(DBPF::SafeSpanReader& reader) {
    auto byte0 = reader.ReadLE<uint8_t>();
    if (!byte0) return std::unexpected(byte0.error());
    auto byte1 = reader.ReadLE<uint8_t>();
    if (!byte1) return std::unexpected(byte1.error());
    auto byte2 = reader.ReadLE<uint8_t>();
    if (!byte2) return std::unexpected(byte2.error());

    uint32_t result = (static_cast<uint32_t>(*byte0) << 16) |
                      (static_cast<uint32_t>(*byte1) << 8) |
                      static_cast<uint32_t>(*byte2);
    return result;
}

std::string MakeName(const char name[4]) {
    std::string s(name, name + 4);
    auto nullPos = s.find('\0');
    if (nullPos != std::string::npos) {
        s.resize(nullPos);
    }
    return s;
}

} // namespace

namespace FSH {

ParseExpected<Record> Reader::Parse(std::span<const uint8_t> buffer) {
    if (buffer.size() < sizeof(FileHeader)) {
        return Fail("Buffer too small for FSH header");
    }

    std::vector<uint8_t> decompressed;
    std::span<const uint8_t> fileSpan = buffer;

    if (QFS::Decompressor::IsQFSCompressed(buffer)) {
        auto result = QFS::Decompressor::Decompress(buffer, decompressed);
        if (!result.has_value()) {
            return Fail("Failed to decompress FSH payload: {}", result.error().message);
        }
        fileSpan = std::span<const uint8_t>(decompressed.data(), decompressed.size());
    }

    DBPF::SafeSpanReader reader(fileSpan);

    Record outFile;
    auto magic = reader.ReadLE<uint32_t>();
    if (!magic) return std::unexpected(magic.error());
    outFile.header.magic = *magic;

    auto size = reader.ReadLE<uint32_t>();
    if (!size) return std::unexpected(size.error());
    outFile.header.size = *size;

    auto numEntries = reader.ReadLE<uint32_t>();
    if (!numEntries) return std::unexpected(numEntries.error());
    outFile.header.numEntries = *numEntries;

    auto dirId = reader.ReadLE<uint32_t>();
    if (!dirId) return std::unexpected(dirId.error());
    outFile.header.dirId = *dirId;

    if (!outFile.header.IsValid()) {
        return Fail("Invalid FSH header");
    }

    struct DirEntryParsed {
        std::string name;
        uint32_t offset{};
    };

    std::vector<DirEntryParsed> directory(outFile.header.numEntries);
    for (uint32_t i = 0; i < outFile.header.numEntries; ++i) {
        DirectoryEntry dir{};
        auto readBytes = reader.ReadBytes(dir.name, sizeof(dir.name));
        if (!readBytes) return std::unexpected(readBytes.error());

        auto offset = reader.ReadLE<uint32_t>();
        if (!offset) return std::unexpected(offset.error());

        directory[i].name = MakeName(dir.name);
        directory[i].offset = *offset;
    }

    outFile.entries.clear();
    outFile.entries.reserve(outFile.header.numEntries);

    for (uint32_t i = 0; i < outFile.header.numEntries; ++i) {
        const uint32_t offset = directory[i].offset;
        const uint32_t nextOffset = (i + 1 < directory.size())
                                        ? directory[i + 1].offset
                                        : static_cast<uint32_t>(fileSpan.size());
        if (offset >= fileSpan.size() || offset >= nextOffset) {
            return Fail("Invalid FSH directory offsets");
        }

        // Create a reader for this entry's data
        auto entrySpan = fileSpan.subspan(offset, nextOffset - offset);
        DBPF::SafeSpanReader entryReader(entrySpan);

        Entry entry{};
        entry.name = directory[i].name;

        auto record = entryReader.ReadLE<uint8_t>();
        if (!record) return std::unexpected(record.error());

        auto blockSize = ReadUInt24(entryReader);
        if (!blockSize) return std::unexpected(blockSize.error());

        auto width = entryReader.ReadLE<uint16_t>();
        if (!width) return std::unexpected(width.error());
        auto height = entryReader.ReadLE<uint16_t>();
        if (!height) return std::unexpected(height.error());
        auto xCenter = entryReader.ReadLE<uint16_t>();
        if (!xCenter) return std::unexpected(xCenter.error());
        auto yCenter = entryReader.ReadLE<uint16_t>();
        if (!yCenter) return std::unexpected(yCenter.error());
        auto xOffset = entryReader.ReadLE<uint16_t>();
        if (!xOffset) return std::unexpected(xOffset.error());
        auto yOffset = entryReader.ReadLE<uint16_t>();
        if (!yOffset) return std::unexpected(yOffset.error());

        entry.formatCode = *record & 0x7F;
        entry.width = *width;
        entry.height = *height;
        entry.mipCount = static_cast<uint8_t>((*yOffset >> 12) & 0x0F);

        for (uint8_t mip = 0; mip <= entry.mipCount; ++mip) {
            uint16_t mipWidth = static_cast<uint16_t>(std::max<int>(1, *width >> mip));
            uint16_t mipHeight = static_cast<uint16_t>(std::max<int>(1, *height >> mip));
            if ((entry.formatCode == kCodeDXT1 || entry.formatCode == kCodeDXT3) &&
                (mipWidth % 4 != 0 || mipHeight % 4 != 0)) {
                break;
            }
            Bitmap bitmap;
            bitmap.code = entry.formatCode;
            bitmap.width = mipWidth;
            bitmap.height = mipHeight;
            bitmap.mipLevel = mip;
            const size_t dataSize = bitmap.ExpectedDataSize();

            auto bitmapData = entryReader.PeekBytes(dataSize);
            if (!bitmapData) return std::unexpected(bitmapData.error());

            bitmap.data.assign(bitmapData->begin(), bitmapData->end());
            auto skip = entryReader.Skip(dataSize);
            if (!skip) return std::unexpected(skip.error());

            entry.bitmaps.push_back(std::move(bitmap));
        }

        if (*blockSize != 0) {
            const uint32_t attachmentOffset = offset + *blockSize;
            if (attachmentOffset + 4 < nextOffset) {
                // Use the original fileSpan to access the attachment
                auto attachmentSpan = fileSpan.subspan(attachmentOffset, nextOffset - attachmentOffset);
                if (attachmentSpan.size() >= 5 && attachmentSpan[0] == 0x70) {
                    auto labelStart = reinterpret_cast<const char*>(attachmentSpan.data() + 4);
                    auto labelEnd = reinterpret_cast<const char*>(attachmentSpan.data() + attachmentSpan.size());
                    const char* terminator = std::find(labelStart, labelEnd, '\0');
                    entry.label.assign(labelStart, terminator);
                }
            }
        }

        outFile.entries.push_back(std::move(entry));
    }

    return outFile;
}

bool Reader::ConvertToRGBA8(const Bitmap& bitmap, std::vector<uint8_t>& outRGBA) {
    if (bitmap.width == 0 || bitmap.height == 0) {
        return false;
    }

    const size_t pixelCount = static_cast<size_t>(bitmap.width) * static_cast<size_t>(bitmap.height);
    outRGBA.assign(pixelCount * 4, 0);

    if (bitmap.IsDXT()) {
        if (bitmap.width % 4 != 0 || bitmap.height % 4 != 0) {
            return false;
        }
    }

    switch (bitmap.code) {
        case kCode32Bit: {
            const uint8_t* src = bitmap.data.data();
            uint8_t* dst = outRGBA.data();
            for (size_t i = 0; i < pixelCount; ++i) {
                uint8_t b = *src++;
                uint8_t g = *src++;
                uint8_t r = *src++;
                uint8_t a = *src++;
                *dst++ = r;
                *dst++ = g;
                *dst++ = b;
                *dst++ = a;
            }
            return true;
        }
        case kCode24Bit: {
            const uint8_t* src = bitmap.data.data();
            uint8_t* dst = outRGBA.data();
            for (size_t i = 0; i < pixelCount; ++i) {
                uint8_t b = *src++;
                uint8_t g = *src++;
                uint8_t r = *src++;
                *dst++ = r;
                *dst++ = g;
                *dst++ = b;
                *dst++ = 255;
            }
            return true;
        }
        case kCode4444: {
            const uint8_t* src = bitmap.data.data();
            uint8_t* dst = outRGBA.data();
            for (size_t i = 0; i < pixelCount; ++i) {
                uint16_t color;
                std::memcpy(&color, src, sizeof(uint16_t));
                src += sizeof(uint16_t);
                Reader::ARGB4444ToRGBA8(color, dst);
                dst += 4;
            }
            return true;
        }
        case kCode0565: {
            const uint8_t* src = bitmap.data.data();
            uint8_t* dst = outRGBA.data();
            for (size_t i = 0; i < pixelCount; ++i) {
                uint16_t color;
                std::memcpy(&color, src, sizeof(uint16_t));
                src += sizeof(uint16_t);
                Reader::RGB565ToRGBA8(color, dst);
                dst += 4;
            }
            return true;
        }
        case kCode1555: {
            const uint8_t* src = bitmap.data.data();
            uint8_t* dst = outRGBA.data();
            for (size_t i = 0; i < pixelCount; ++i) {
                uint16_t color;
                std::memcpy(&color, src, sizeof(uint16_t));
                src += sizeof(uint16_t);
                Reader::ARGB1555ToRGBA8(color, dst);
                dst += 4;
            }
            return true;
        }
        case kCodeDXT1:
        case kCodeDXT3:
        case kCodeDXT5: {
            int squishFlags = squish::kDxt1;
            if (bitmap.code == kCodeDXT3) {
                squishFlags = squish::kDxt3;
            } else if (bitmap.code == kCodeDXT5) {
                squishFlags = squish::kDxt5;
            }
            squish::DecompressImage(outRGBA.data(),
                                    static_cast<int>(bitmap.width),
                                    static_cast<int>(bitmap.height),
                                    bitmap.data.data(),
                                    squishFlags);
            return true;
        }
        default:
            return false;
    }
}

void Reader::ARGB4444ToRGBA8(uint16_t color, uint8_t* rgba) {
    uint8_t a = (color >> 12) & 0xF;
    uint8_t r = (color >> 8) & 0xF;
    uint8_t g = (color >> 4) & 0xF;
    uint8_t b = color & 0xF;
    rgba[0] = static_cast<uint8_t>((r << 4) | r);
    rgba[1] = static_cast<uint8_t>((g << 4) | g);
    rgba[2] = static_cast<uint8_t>((b << 4) | b);
    rgba[3] = static_cast<uint8_t>((a << 4) | a);
}

void Reader::RGB565ToRGBA8(uint16_t color, uint8_t* rgba) {
    uint8_t r = (color >> 11) & 0x1F;
    uint8_t g = (color >> 5) & 0x3F;
    uint8_t b = color & 0x1F;
    rgba[0] = static_cast<uint8_t>((r << 3) | (r >> 2));
    rgba[1] = static_cast<uint8_t>((g << 2) | (g >> 4));
    rgba[2] = static_cast<uint8_t>((b << 3) | (b >> 2));
    rgba[3] = 255;
}

void Reader::ARGB1555ToRGBA8(uint16_t color, uint8_t* rgba) {
    uint8_t a = (color >> 15) & 0x1;
    uint8_t r = (color >> 10) & 0x1F;
    uint8_t g = (color >> 5) & 0x1F;
    uint8_t b = color & 0x1F;
    rgba[0] = static_cast<uint8_t>((r << 3) | (r >> 2));
    rgba[1] = static_cast<uint8_t>((g << 3) | (g >> 2));
    rgba[2] = static_cast<uint8_t>((b << 3) | (b >> 2));
    rgba[3] = a ? 255 : 0;
}

} // namespace FSH
