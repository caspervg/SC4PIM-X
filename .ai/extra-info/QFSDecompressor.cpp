#include "QFSDecompressor.h"

#include <cstring>
namespace {

    inline uint32_t Read24BE(const uint8_t* data) {
        return (static_cast<uint32_t>(data[2]) << 16) |
               (static_cast<uint32_t>(data[3]) << 8) |
               static_cast<uint32_t>(data[4]);
    }

    inline void CopyLiteral(const uint8_t* src, uint8_t* dest, size_t len) {
        if (len == 0) {
            return;
        }
        std::memcpy(dest, src, len);
    }

    ParseExpected<void> OffsetCopy(uint8_t* buffer, int destPos, int offset, int len) {
        if (offset <= 0 || offset > destPos) {
            return Fail("Invalid QFS offset {} at dest {}", offset, destPos);
        }
        int srcPos = destPos - offset;
        for (int i = 0; i < len; ++i) {
            buffer[destPos + i] = buffer[srcPos + i];
        }
        return {};
    }

} // namespace

namespace QFS {

    ParseExpected<size_t> Decompressor::Decompress(std::span<const uint8_t> input, std::vector<uint8_t>& output) {
        if (input.size() < 5) {
            return Fail("QFS payload too small ({} bytes)", input.size());
        }

        const uint8_t* data = input.data();
        const size_t size = input.size();

        const uint16_t magic = static_cast<uint16_t>((static_cast<uint16_t>(data[0] & 0xFE) << 8) | data[1]);
        if (magic != MAGIC_COMPRESSED) {
            return Fail("QFS magic mismatch: expected 0x{:04X}, got 0x{:04X}", MAGIC_COMPRESSED, magic);
        }

        const uint32_t uncompressedSize = Read24BE(data);
        output.assign(uncompressedSize, 0);
        if (uncompressedSize == 0) {
            return static_cast<size_t>(0);
        }

        auto result = DecompressInternal(data, size, output.data(), uncompressedSize);
        if (!result.has_value()) {
            output.clear();
            return std::unexpected(result.error());
        }

        return static_cast<size_t>(uncompressedSize);
    }

    bool Decompressor::IsQFSCompressed(std::span<const uint8_t> buffer) {
        if (buffer.size() < 5) {
            return false;
        }
        const uint8_t* data = buffer.data();
        return ((static_cast<uint16_t>(data[0] & 0xFE) << 8) | data[1]) == MAGIC_COMPRESSED;
    }

    uint32_t Decompressor::GetUncompressedSize(std::span<const uint8_t> buffer) {
        if (!IsQFSCompressed(buffer)) {
            return 0;
        }
        return Read24BE(buffer.data());
    }

    ParseExpected<void> Decompressor::DecompressInternal(const uint8_t* input, size_t inputSize,
                                                         uint8_t* output, size_t outputSize) {
        int inPos = (input[0] & 0x01) ? 8 : 5;
        int outPos = 0;
        int control1 = 0;

        while (inPos < static_cast<int>(inputSize) && control1 < 0xFC) {
            if (inPos >= static_cast<int>(inputSize)) {
                return Fail("QFS truncated while reading control byte");
            }
            control1 = input[inPos++] & 0xFF;

            if (control1 <= 0x7F) {
                if (inPos >= static_cast<int>(inputSize)) {
                    return Fail("QFS truncated in control1<=0x7F block");
                }
                int control2 = input[inPos++] & 0xFF;
                int literalLen = control1 & 0x03;
                if (inPos + literalLen > static_cast<int>(inputSize)) {
                    return Fail("QFS literal overruns input (short block)");
                }
                if (outPos + literalLen > static_cast<int>(outputSize)) {
                    return Fail("QFS literal overruns output (short block)");
                }
                CopyLiteral(input + inPos, output + outPos, literalLen);
                outPos += literalLen;
                inPos += literalLen;

                int offset = ((control1 & 0x60) << 3) + control2 + 1;
                int copyLen = ((control1 & 0x1C) >> 2) + 3;
                if (outPos + copyLen > static_cast<int>(outputSize)) {
                    return Fail("QFS copy overruns output (short block)");
                }
                if (auto status = OffsetCopy(output, outPos, offset, copyLen); !status.has_value()) {
                    return status;
                }
                outPos += copyLen;
            } else if (control1 <= 0xBF) {
                if (inPos + 1 >= static_cast<int>(inputSize)) {
                    return Fail("QFS truncated in control1<=0xBF block");
                }
                int control2 = input[inPos++] & 0xFF;
                int control3 = input[inPos++] & 0xFF;

                int literalLen = (control2 >> 6) & 0x03;
                if (inPos + literalLen > static_cast<int>(inputSize)) {
                    return Fail("QFS literal overruns input (mid block)");
                }
                if (outPos + literalLen > static_cast<int>(outputSize)) {
                    return Fail("QFS literal overruns output (mid block)");
                }
                CopyLiteral(input + inPos, output + outPos, literalLen);
                outPos += literalLen;
                inPos += literalLen;

                int offset = ((control2 & 0x3F) << 8) + control3 + 1;
                int copyLen = (control1 & 0x3F) + 4;
                if (outPos + copyLen > static_cast<int>(outputSize)) {
                    return Fail("QFS copy overruns output (mid block)");
                }
                if (auto status = OffsetCopy(output, outPos, offset, copyLen); !status.has_value()) {
                    return status;
                }
                outPos += copyLen;
            } else if (control1 <= 0xDF) {
                if (inPos + 2 >= static_cast<int>(inputSize)) {
                    return Fail("QFS truncated in control1<=0xDF block");
                }
                int control2 = input[inPos++] & 0xFF;
                int control3 = input[inPos++] & 0xFF;
                int control4 = input[inPos++] & 0xFF;

                int literalLen = control1 & 0x03;
                if (inPos + literalLen > static_cast<int>(inputSize)) {
                    return Fail("QFS literal overruns input (long block)");
                }
                if (outPos + literalLen > static_cast<int>(outputSize)) {
                    return Fail("QFS literal overruns output (long block)");
                }
                CopyLiteral(input + inPos, output + outPos, literalLen);
                outPos += literalLen;
                inPos += literalLen;

                int offset = ((control1 & 0x10) << 12) + (control2 << 8) + control3 + 1;
                int copyLen = ((control1 & 0x0C) << 6) + control4 + 5;
                if (outPos + copyLen > static_cast<int>(outputSize)) {
                    return Fail("QFS copy overruns output (long block)");
                }
                if (auto status = OffsetCopy(output, outPos, offset, copyLen); !status.has_value()) {
                    return status;
                }
                outPos += copyLen;
            } else if (control1 <= 0xFB) {
                int literalLen = ((control1 & 0x1F) << 2) + 4;
                if (inPos + literalLen > static_cast<int>(inputSize)) {
                    return Fail("QFS literal overruns input (raw block)");
                }
                if (outPos + literalLen > static_cast<int>(outputSize)) {
                    return Fail("QFS literal overruns output (raw block)");
                }
                CopyLiteral(input + inPos, output + outPos, literalLen);
                outPos += literalLen;
                inPos += literalLen;
            } else {
                int literalLen = control1 & 0x03;
                if (inPos + literalLen > static_cast<int>(inputSize)) {
                    return Fail("QFS literal overruns input (terminator block)");
                }
                if (outPos + literalLen > static_cast<int>(outputSize)) {
                    return Fail("QFS literal overruns output (terminator block)");
                }
                CopyLiteral(input + inPos, output + outPos, literalLen);
                outPos += literalLen;
                inPos += literalLen;
                break;
            }
        }

        if (static_cast<size_t>(outPos) != outputSize) {
            return Fail("QFS decompression wrote {} bytes but expected {}", outPos, outputSize);
        }
        return {};
    }

} // namespace QFS