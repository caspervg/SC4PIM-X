/* Optional native accelerator for sc4pimx.QFS.
 *
 * decode() / encode() mirror the pure-Python sc4pimx.QFS reference codec
 * byte-for-byte (same greedy parse, same packet choices), so the two are
 * interchangeable: QFS.py imports this module when present and falls back to
 * the pure-Python implementation otherwise.
 */
#define Py_LIMITED_API 0x030B0000
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <string.h>

static PyObject *qfs_decode(PyObject *self, PyObject *arg) {
    Py_buffer view;
    if (PyObject_GetBuffer(arg, &view, PyBUF_SIMPLE) != 0)
        return NULL;

    const unsigned char *data = (const unsigned char *)view.buf;
    Py_ssize_t n = view.len;

    if (n < 5 || (((data[0] & 0xFE) << 8) | data[1]) != 0x10FB) {
        PyBuffer_Release(&view);
        Py_RETURN_NONE;
    }

    Py_ssize_t size = ((Py_ssize_t)data[2] << 16) | ((Py_ssize_t)data[3] << 8) | data[4];
    Py_ssize_t p = (data[0] & 0x01) ? 8 : 5;
    if (p > n) {
        PyBuffer_Release(&view);
        Py_RETURN_NONE;
    }

    unsigned char *out = (unsigned char *)PyMem_Malloc(size ? (size_t)size : 1);
    if (!out) {
        PyBuffer_Release(&view);
        return PyErr_NoMemory();
    }
    Py_ssize_t out_pos = 0;

#define FAIL() do { PyMem_Free(out); PyBuffer_Release(&view); Py_RETURN_NONE; } while (0)

    for (;;) {
        if (p >= n)
            FAIL();

        unsigned int c0 = data[p++];
        Py_ssize_t num_literal, copy_len, copy_offset;

        if (c0 >= 0xFC) {
            num_literal = c0 & 0x03;
            if (p + num_literal > n || out_pos + num_literal > size)
                FAIL();
            if (num_literal) {
                memcpy(out + out_pos, data + p, (size_t)num_literal);
                out_pos += num_literal;
            }
            if (out_pos != size)
                FAIL();
            PyObject *res = PyBytes_FromStringAndSize((const char *)out, size);
            PyMem_Free(out);
            PyBuffer_Release(&view);
            return res;
        }

        if (c0 <= 0x7F) {
            if (p >= n)
                FAIL();
            unsigned int c1 = data[p++];
            num_literal = c0 & 0x03;
            copy_len = ((c0 >> 2) & 0x07) + 3;
            copy_offset = ((c0 & 0x60) << 3) + c1 + 1;
        } else if (c0 <= 0xBF) {
            if (p + 1 >= n)
                FAIL();
            unsigned int c1 = data[p];
            unsigned int c2 = data[p + 1];
            p += 2;
            num_literal = (c1 >> 6) & 0x03;
            copy_len = (c0 & 0x3F) + 4;
            copy_offset = ((c1 & 0x3F) << 8) + c2 + 1;
        } else if (c0 <= 0xDF) {
            if (p + 2 >= n)
                FAIL();
            unsigned int c1 = data[p];
            unsigned int c2 = data[p + 1];
            unsigned int c3 = data[p + 2];
            p += 3;
            num_literal = c0 & 0x03;
            copy_len = ((c0 & 0x0C) << 6) + c3 + 5;
            copy_offset = ((c0 & 0x10) << 12) + (c1 << 8) + c2 + 1;
        } else {
            num_literal = ((c0 & 0x1F) << 2) + 4;
            if (p + num_literal > n || out_pos + num_literal > size)
                FAIL();
            memcpy(out + out_pos, data + p, (size_t)num_literal);
            p += num_literal;
            out_pos += num_literal;
            continue;
        }

        if (p + num_literal > n)
            FAIL();
        Py_ssize_t packet_len = num_literal + copy_len;
        if (copy_offset > out_pos + num_literal || out_pos + packet_len > size)
            FAIL();

        if (num_literal) {
            memcpy(out + out_pos, data + p, (size_t)num_literal);
            p += num_literal;
            out_pos += num_literal;
        }

        unsigned char *d = out + out_pos;
        const unsigned char *s = d - copy_offset;
        if (copy_offset >= copy_len) {
            memcpy(d, s, (size_t)copy_len);
        } else {
            for (Py_ssize_t i = 0; i < copy_len; i++)
                d[i] = s[i];
        }
        out_pos += copy_len;
    }
#undef FAIL
}

#define ENC_HASH_BITS 16
#define ENC_HASH_SIZE (1 << ENC_HASH_BITS)
#define ENC_HASH_MASK (ENC_HASH_SIZE - 1)
#define ENC_MAX_OFFSET 131072
#define ENC_MAX_COPY 1028
#define ENC_MAX_CHAIN 96
#define ENC_NICE_MATCH 256
#define ENC_INSERT_LIMIT 64
#define ENC_MIN_MATCH 3
#define ENC_MAX_SIZE 0xFFFFFF

#define HASH3(d, i) ((((unsigned)(d)[i] << 8) ^ ((unsigned)(d)[(i) + 1] << 4) ^ (unsigned)(d)[(i) + 2]) & ENC_HASH_MASK)

static PyObject *qfs_encode(PyObject *self, PyObject *arg) {
    Py_buffer view;
    if (PyObject_GetBuffer(arg, &view, PyBUF_SIMPLE) != 0)
        return NULL;

    const unsigned char *data = (const unsigned char *)view.buf;
    Py_ssize_t n = view.len;

    if (n > ENC_MAX_SIZE) {
        PyBuffer_Release(&view);
        Py_RETURN_NONE;
    }

    /* Bounded worst case: header + every byte as a literal run + terminator. */
    size_t cap = (size_t)n + (size_t)n / 50 + 128;
    unsigned char *out = (unsigned char *)PyMem_Malloc(cap);
    if (!out) {
        PyBuffer_Release(&view);
        return PyErr_NoMemory();
    }
    Py_ssize_t op = 0;
    out[op++] = 0x10;
    out[op++] = 0xFB;
    out[op++] = (unsigned char)((n >> 16) & 0xFF);
    out[op++] = (unsigned char)((n >> 8) & 0xFF);
    out[op++] = (unsigned char)(n & 0xFF);

    if (n == 0) {
        out[op++] = 0xFC;
        PyObject *res = PyBytes_FromStringAndSize((const char *)out, op);
        PyMem_Free(out);
        PyBuffer_Release(&view);
        return res;
    }

    int *head = (int *)PyMem_Malloc(sizeof(int) * ENC_HASH_SIZE);
    int *prev = (int *)PyMem_Malloc(sizeof(int) * (size_t)n);
    if (!head || !prev) {
        PyMem_Free(head);
        PyMem_Free(prev);
        PyMem_Free(out);
        PyBuffer_Release(&view);
        return PyErr_NoMemory();
    }
    for (Py_ssize_t i = 0; i < ENC_HASH_SIZE; i++)
        head[i] = -1;

    Py_ssize_t last_hash_pos = n - ENC_MIN_MATCH;
    Py_ssize_t pos = 0;
    Py_ssize_t literal_start = 0;

    while (pos <= last_hash_pos) {
        unsigned int b0 = data[pos], b1 = data[pos + 1], b2 = data[pos + 2];
        unsigned int h = ((b0 << 8) ^ (b1 << 4) ^ b2) & ENC_HASH_MASK;
        int candidate = head[h];

        Py_ssize_t best_len = 0, best_offset = 0;

        if (candidate >= 0) {
            Py_ssize_t max_len = n - pos;
            if (max_len > ENC_MAX_COPY)
                max_len = ENC_MAX_COPY;
            if (max_len >= ENC_MIN_MATCH) {
                Py_ssize_t min_candidate = pos - ENC_MAX_OFFSET;
                if (min_candidate < 0)
                    min_candidate = 0;
                Py_ssize_t best_score = 0;
                int steps = ENC_MAX_CHAIN;

                while (candidate >= min_candidate && steps) {
                    steps--;
                    if (data[candidate] == b0 && data[candidate + 1] == b1 && data[candidate + 2] == b2) {
                        Py_ssize_t offset = pos - candidate;
                        Py_ssize_t min_len = (offset <= 1024) ? 3 : (offset <= 16384) ? 4 : 5;
                        if (max_len >= min_len) {
                            Py_ssize_t length = ENC_MIN_MATCH;
                            while (length < max_len && data[candidate + length] == data[pos + length])
                                length++;
                            if (length >= min_len) {
                                Py_ssize_t score;
                                if (length <= 10 && offset <= 1024)
                                    score = length - 2;
                                else if (length <= 67 && offset <= 16384)
                                    score = length - 3;
                                else
                                    score = length - 4;
                                if (score > best_score || (score == best_score && length > best_len)) {
                                    best_len = length;
                                    best_offset = offset;
                                    best_score = score;
                                    if (length == max_len || length >= ENC_NICE_MATCH)
                                        break;
                                }
                            }
                        }
                    }
                    candidate = prev[candidate];
                }
            }
        }

        if (best_len) {
            /* flush pending literals (_emit_pending_literals + _emit_literal_runs) */
            Py_ssize_t lit_len = pos - literal_start;
            Py_ssize_t flush_end = pos - (lit_len & 3);
            Py_ssize_t lp = literal_start;
            while (lp < flush_end) {
                Py_ssize_t chunk = flush_end - lp;
                if (chunk > 112)
                    chunk = 112;
                out[op++] = (unsigned char)(0xE0 | ((chunk - 4) >> 2));
                memcpy(out + op, data + lp, (size_t)chunk);
                op += chunk;
                lp += chunk;
            }
            literal_start = flush_end;
            Py_ssize_t literal_count = pos - literal_start;

            /* _emit_copy_packet */
            Py_ssize_t offset = best_offset - 1;
            if (best_offset <= 1024 && best_len <= 10) {
                out[op++] = (unsigned char)(((offset >> 8) << 5) | ((best_len - 3) << 2) | literal_count);
                out[op++] = (unsigned char)(offset & 0xFF);
            } else if (best_offset <= 16384 && best_len <= 67) {
                out[op++] = (unsigned char)(0x80 | (best_len - 4));
                out[op++] = (unsigned char)((literal_count << 6) | ((offset >> 8) & 0x3F));
                out[op++] = (unsigned char)(offset & 0xFF);
            } else {
                Py_ssize_t length = best_len - 5;
                out[op++] = (unsigned char)(0xC0 | literal_count | ((length >> 8) << 2) | ((offset >> 16) << 4));
                out[op++] = (unsigned char)((offset >> 8) & 0xFF);
                out[op++] = (unsigned char)(offset & 0xFF);
                out[op++] = (unsigned char)(length & 0xFF);
            }
            if (literal_count) {
                memcpy(out + op, data + literal_start, (size_t)literal_count);
                op += literal_count;
            }

            /* insert pos, then up to INSERT_LIMIT positions inside the match */
            prev[pos] = head[h];
            head[h] = (int)pos;
            Py_ssize_t insert_end = pos + best_len;
            if (insert_end > last_hash_pos + 1)
                insert_end = last_hash_pos + 1;
            if (insert_end > pos + 1) {
                Py_ssize_t insert_start = insert_end - ENC_INSERT_LIMIT;
                if (insert_start < pos + 1)
                    insert_start = pos + 1;
                for (Py_ssize_t ip = insert_start; ip < insert_end; ip++) {
                    unsigned int hh = HASH3(data, ip);
                    prev[ip] = head[hh];
                    head[hh] = (int)ip;
                }
            }

            pos += best_len;
            literal_start = pos;
        } else {
            prev[pos] = head[h];
            head[h] = (int)pos;
            pos++;
        }
    }

    /* _emit_final_literals */
    {
        Py_ssize_t lit_len = n - literal_start;
        Py_ssize_t terminal = lit_len & 3;
        Py_ssize_t flush_end = n - terminal;
        Py_ssize_t lp = literal_start;
        while (lp < flush_end) {
            Py_ssize_t chunk = flush_end - lp;
            if (chunk > 112)
                chunk = 112;
            out[op++] = (unsigned char)(0xE0 | ((chunk - 4) >> 2));
            memcpy(out + op, data + lp, (size_t)chunk);
            op += chunk;
            lp += chunk;
        }
        out[op++] = (unsigned char)(0xFC | terminal);
        if (terminal) {
            memcpy(out + op, data + flush_end, (size_t)terminal);
            op += terminal;
        }
    }

    PyMem_Free(head);
    PyMem_Free(prev);
    PyObject *res = PyBytes_FromStringAndSize((const char *)out, op);
    PyMem_Free(out);
    PyBuffer_Release(&view);
    return res;
}

static PyMethodDef methods[] = {
    {"decode", qfs_decode, METH_O, "Decompress a QFS/RefPack stream; None on invalid input."},
    {"encode", qfs_encode, METH_O, "Compress bytes to a QFS/RefPack stream; None if too large."},
    {NULL, NULL, 0, NULL},
};

static struct PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT, "_qfs", NULL, -1, methods,
};

PyMODINIT_FUNC PyInit__qfs(void) {
    return PyModule_Create(&moduledef);
}
