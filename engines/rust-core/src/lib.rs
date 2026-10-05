//! Ithute safe native accelerator.
//!
//! Keep the exported ABI tiny. Python owns business decisions; this library
//! receives bounded byte buffers for CPU-oriented processing.

#[repr(C)]
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct ByteStats {
    pub bytes: usize,
    pub lines: usize,
    pub ascii: usize,
    pub non_ascii: usize,
}

#[no_mangle]
pub unsafe extern "C" fn ithute_rust_byte_stats(
    data: *const u8,
    len: usize,
    out: *mut ByteStats,
) -> i32 {
    if out.is_null() || (data.is_null() && len != 0) {
        return 1;
    }

    let bytes = if len == 0 {
        &[][..]
    } else {
        std::slice::from_raw_parts(data, len)
    };
    let ascii = bytes.iter().filter(|value| value.is_ascii()).count();
    let lines = if bytes.is_empty() {
        0
    } else {
        bytes.iter().filter(|value| **value == b'\n').count() + 1
    };

    *out = ByteStats {
        bytes: len,
        lines,
        ascii,
        non_ascii: len.saturating_sub(ascii),
    };
    0
}


#[repr(C)]
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct MimeScan {
    pub bytes: usize,
    pub header_bytes: usize,
    pub body_bytes: usize,
    pub lines: usize,
    pub crlf_lines: usize,
    pub non_ascii: usize,
    pub nul_bytes: usize,
    pub boundary_markers: usize,
    pub attachment_signals: usize,
}

fn ascii_lower(value: u8) -> u8 {
    if value.is_ascii_uppercase() {
        value + 32
    } else {
        value
    }
}

fn contains_ascii_case_insensitive(haystack: &[u8], needle: &[u8]) -> bool {
    if needle.is_empty() {
        return true;
    }
    if haystack.len() < needle.len() {
        return false;
    }
    haystack.windows(needle.len()).any(|window| {
        window.iter().zip(needle.iter()).all(|(left, right)| ascii_lower(*left) == ascii_lower(*right))
    })
}

fn mime_scan(bytes: &[u8]) -> MimeScan {
    let mut split = None;
    if bytes.len() >= 4 {
        split = bytes.windows(4).position(|window| window == b"\r\n\r\n").map(|index| (index + 4, 4));
    }
    if split.is_none() && bytes.len() >= 2 {
        split = bytes.windows(2).position(|window| window == b"\n\n").map(|index| (index + 2, 2));
    }

    let header_bytes = split.map(|(index, _)| index).unwrap_or(bytes.len());
    let body_bytes = bytes.len().saturating_sub(header_bytes);
    let lines = if bytes.is_empty() { 0 } else { bytes.iter().filter(|value| **value == b'\n').count() + 1 };
    let crlf_lines = bytes.windows(2).filter(|window| *window == b"\r\n").count();
    let non_ascii = bytes.iter().filter(|value| !value.is_ascii()).count();
    let nul_bytes = bytes.iter().filter(|value| **value == 0).count();

    let boundary_markers = bytes
        .split(|value| *value == b'\n')
        .filter(|line| {
            let trimmed = line.iter().position(|value| *value != b'\r').map(|index| &line[index..]).unwrap_or(&[]);
            trimmed.starts_with(b"--")
        })
        .count();

    // Deliberately conservative. A zero means the Python MIME tree cannot
    // expose an attachment through filename/name or Content-Disposition.
    // False positives only cause the authoritative Python walk to run.
    let attachment_signals = usize::from(
        contains_ascii_case_insensitive(bytes, b"content-disposition")
            || contains_ascii_case_insensitive(bytes, b"filename")
            || contains_ascii_case_insensitive(bytes, b"name"),
    );

    MimeScan {
        bytes: bytes.len(),
        header_bytes,
        body_bytes,
        lines,
        crlf_lines,
        non_ascii,
        nul_bytes,
        boundary_markers,
        attachment_signals,
    }
}

#[no_mangle]
pub unsafe extern "C" fn ithute_rust_mime_scan(
    data: *const u8,
    len: usize,
    out: *mut MimeScan,
) -> i32 {
    if out.is_null() || (data.is_null() && len != 0) {
        return 1;
    }
    let bytes = if len == 0 {
        &[][..]
    } else {
        std::slice::from_raw_parts(data, len)
    };
    *out = mime_scan(bytes);
    0
}


const SHA256_INITIAL: [u32; 8] = [
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
    0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
];

const SHA256_K: [u32; 64] = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
];

fn sha256_compress(state: &mut [u32; 8], block: &[u8]) {
    let mut w = [0u32; 64];
    for (index, chunk) in block.chunks_exact(4).take(16).enumerate() {
        w[index] = u32::from_be_bytes([chunk[0], chunk[1], chunk[2], chunk[3]]);
    }
    for index in 16..64 {
        let s0 = w[index - 15].rotate_right(7) ^ w[index - 15].rotate_right(18) ^ (w[index - 15] >> 3);
        let s1 = w[index - 2].rotate_right(17) ^ w[index - 2].rotate_right(19) ^ (w[index - 2] >> 10);
        w[index] = w[index - 16]
            .wrapping_add(s0)
            .wrapping_add(w[index - 7])
            .wrapping_add(s1);
    }

    let mut a = state[0];
    let mut b = state[1];
    let mut c = state[2];
    let mut d = state[3];
    let mut e = state[4];
    let mut f = state[5];
    let mut g = state[6];
    let mut h = state[7];

    for index in 0..64 {
        let big_s1 = e.rotate_right(6) ^ e.rotate_right(11) ^ e.rotate_right(25);
        let choose = (e & f) ^ ((!e) & g);
        let temp1 = h
            .wrapping_add(big_s1)
            .wrapping_add(choose)
            .wrapping_add(SHA256_K[index])
            .wrapping_add(w[index]);
        let big_s0 = a.rotate_right(2) ^ a.rotate_right(13) ^ a.rotate_right(22);
        let majority = (a & b) ^ (a & c) ^ (b & c);
        let temp2 = big_s0.wrapping_add(majority);

        h = g;
        g = f;
        f = e;
        e = d.wrapping_add(temp1);
        d = c;
        c = b;
        b = a;
        a = temp1.wrapping_add(temp2);
    }

    state[0] = state[0].wrapping_add(a);
    state[1] = state[1].wrapping_add(b);
    state[2] = state[2].wrapping_add(c);
    state[3] = state[3].wrapping_add(d);
    state[4] = state[4].wrapping_add(e);
    state[5] = state[5].wrapping_add(f);
    state[6] = state[6].wrapping_add(g);
    state[7] = state[7].wrapping_add(h);
}

fn sha256_digest(bytes: &[u8]) -> [u8; 32] {
    let mut state = SHA256_INITIAL;
    for block in bytes.chunks_exact(64) {
        sha256_compress(&mut state, block);
    }

    let remainder = bytes.len() % 64;
    let mut tail = [0u8; 128];
    tail[..remainder].copy_from_slice(&bytes[bytes.len() - remainder..]);
    tail[remainder] = 0x80;
    let bit_len = (bytes.len() as u64).wrapping_mul(8);
    let padded_len = if remainder < 56 { 64 } else { 128 };
    tail[padded_len - 8..padded_len].copy_from_slice(&bit_len.to_be_bytes());
    for block in tail[..padded_len].chunks_exact(64) {
        sha256_compress(&mut state, block);
    }

    let mut digest = [0u8; 32];
    for (index, value) in state.iter().enumerate() {
        digest[index * 4..index * 4 + 4].copy_from_slice(&value.to_be_bytes());
    }
    digest
}

fn hmac_sha256(key: &[u8], data: &[u8]) -> [u8; 32] {
    let mut key_block = [0u8; 64];
    if key.len() > 64 {
        let digest = sha256_digest(key);
        key_block[..digest.len()].copy_from_slice(&digest);
    } else {
        key_block[..key.len()].copy_from_slice(key);
    }

    let mut inner_pad = [0u8; 64];
    let mut outer_pad = [0u8; 64];
    for index in 0..64 {
        inner_pad[index] = key_block[index] ^ 0x36;
        outer_pad[index] = key_block[index] ^ 0x5c;
    }

    let mut inner = Vec::with_capacity(64 + data.len());
    inner.extend_from_slice(&inner_pad);
    inner.extend_from_slice(data);
    let inner_digest = sha256_digest(&inner);

    let mut outer = Vec::with_capacity(64 + inner_digest.len());
    outer.extend_from_slice(&outer_pad);
    outer.extend_from_slice(&inner_digest);
    sha256_digest(&outer)
}

#[no_mangle]
pub unsafe extern "C" fn ithute_rust_hmac_sha256(
    key: *const u8,
    key_len: usize,
    data: *const u8,
    data_len: usize,
    out: *mut u8,
) -> i32 {
    if out.is_null() || (key.is_null() && key_len != 0) || (data.is_null() && data_len != 0) {
        return 1;
    }
    let key_bytes = if key_len == 0 {
        &[][..]
    } else {
        std::slice::from_raw_parts(key, key_len)
    };
    let data_bytes = if data_len == 0 {
        &[][..]
    } else {
        std::slice::from_raw_parts(data, data_len)
    };
    let digest = hmac_sha256(key_bytes, data_bytes);
    std::ptr::copy_nonoverlapping(digest.as_ptr(), out, digest.len());
    0
}

#[no_mangle]
pub unsafe extern "C" fn ithute_rust_sha256(
    data: *const u8,
    len: usize,
    out: *mut u8,
) -> i32 {
    if out.is_null() || (data.is_null() && len != 0) {
        return 1;
    }
    let bytes = if len == 0 {
        &[][..]
    } else {
        std::slice::from_raw_parts(data, len)
    };
    let digest = sha256_digest(bytes);
    std::ptr::copy_nonoverlapping(digest.as_ptr(), out, digest.len());
    0
}


#[repr(C)]
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct PushEnvelopeScan {
    pub bytes: usize,
    pub utf8_valid: u8,
    pub json_object_shape: u8,
    pub nul_bytes: usize,
    pub control_bytes: usize,
}

fn push_envelope_scan(bytes: &[u8]) -> PushEnvelopeScan {
    let utf8_valid = std::str::from_utf8(bytes).is_ok();
    let first = bytes.iter().copied().find(|value| !value.is_ascii_whitespace());
    let last = bytes.iter().copied().rev().find(|value| !value.is_ascii_whitespace());
    let json_object_shape = matches!((first, last), (Some(b'{'), Some(b'}')));
    let nul_bytes = bytes.iter().filter(|value| **value == 0).count();
    let control_bytes = bytes
        .iter()
        .filter(|value| **value < 32 && !matches!(**value, b'\t' | b'\n' | b'\r'))
        .count();
    PushEnvelopeScan {
        bytes: bytes.len(),
        utf8_valid: u8::from(utf8_valid),
        json_object_shape: u8::from(json_object_shape),
        nul_bytes,
        control_bytes,
    }
}

#[no_mangle]
pub unsafe extern "C" fn ithute_rust_push_envelope_scan(
    data: *const u8,
    len: usize,
    out: *mut PushEnvelopeScan,
) -> i32 {
    if out.is_null() || (data.is_null() && len != 0) || len > 64 * 1024 {
        return 1;
    }
    let bytes = if len == 0 {
        &[][..]
    } else {
        std::slice::from_raw_parts(data, len)
    };
    *out = push_envelope_scan(bytes);
    0
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn byte_stats_are_deterministic() {
        let raw = b"Subject: hello\n\nBody \xF0\x9F\x93\xA7";
        let mut out = ByteStats::default();
        let code = unsafe { ithute_rust_byte_stats(raw.as_ptr(), raw.len(), &mut out) };
        assert_eq!(code, 0);
        assert_eq!(out.bytes, raw.len());
        assert_eq!(out.lines, 3);
        assert_eq!(out.non_ascii, 4);
    }

    #[test]
    fn mime_scan_finds_structure_and_attachment_signal() {
        let raw = b"From: A <a@example.test>\r\nContent-Type: multipart/mixed; boundary=x\r\n\r\n--x\r\nContent-Disposition: attachment; filename=\"a.txt\"\r\n\r\nhello\r\n--x--\r\n";
        let mut out = MimeScan::default();
        let code = unsafe { ithute_rust_mime_scan(raw.as_ptr(), raw.len(), &mut out) };
        assert_eq!(code, 0);
        assert_eq!(out.bytes, raw.len());
        assert!(out.header_bytes > 0);
        assert_eq!(out.body_bytes, raw.len() - out.header_bytes);
        assert!(out.boundary_markers >= 2);
        assert_eq!(out.attachment_signals, 1);
        assert_eq!(out.nul_bytes, 0);
    }

    #[test]
    fn mime_scan_plain_message_has_no_attachment_signal() {
        let raw = b"From: sender@example.test\r\nSubject: hello\r\n\r\nplain body";
        let mut out = MimeScan::default();
        let code = unsafe { ithute_rust_mime_scan(raw.as_ptr(), raw.len(), &mut out) };
        assert_eq!(code, 0);
        assert_eq!(out.attachment_signals, 0);
        assert_eq!(out.boundary_markers, 0);
    }

    #[test]
    fn sha256_matches_standard_vectors() {
        assert_eq!(
            sha256_digest(b""),
            [
                0xe3, 0xb0, 0xc4, 0x42, 0x98, 0xfc, 0x1c, 0x14,
                0x9a, 0xfb, 0xf4, 0xc8, 0x99, 0x6f, 0xb9, 0x24,
                0x27, 0xae, 0x41, 0xe4, 0x64, 0x9b, 0x93, 0x4c,
                0xa4, 0x95, 0x99, 0x1b, 0x78, 0x52, 0xb8, 0x55,
            ]
        );
        assert_eq!(
            sha256_digest(b"abc"),
            [
                0xba, 0x78, 0x16, 0xbf, 0x8f, 0x01, 0xcf, 0xea,
                0x41, 0x41, 0x40, 0xde, 0x5d, 0xae, 0x22, 0x23,
                0xb0, 0x03, 0x61, 0xa3, 0x96, 0x17, 0x7a, 0x9c,
                0xb4, 0x10, 0xff, 0x61, 0xf2, 0x00, 0x15, 0xad,
            ]
        );
    }

    #[test]
    fn sha256_ffi_writes_digest() {
        let raw = b"ithute";
        let mut out = [0u8; 32];
        let code = unsafe { ithute_rust_sha256(raw.as_ptr(), raw.len(), out.as_mut_ptr()) };
        assert_eq!(code, 0);
        assert_eq!(out, sha256_digest(raw));
    }

    #[test]
    fn hmac_sha256_matches_standard_vector() {
        let digest = hmac_sha256(b"key", b"The quick brown fox jumps over the lazy dog");
        assert_eq!(
            digest,
            [
                0xf7, 0xbc, 0x83, 0xf4, 0x30, 0x53, 0x84, 0x24,
                0xb1, 0x32, 0x98, 0xe6, 0xaa, 0x6f, 0xb1, 0x43,
                0xef, 0x4d, 0x59, 0xa1, 0x49, 0x46, 0x17, 0x59,
                0x97, 0x47, 0x9d, 0xbc, 0x2d, 0x1a, 0x3c, 0xd8,
            ]
        );
    }

    #[test]
    fn hmac_sha256_ffi_writes_digest() {
        let key = b"ithute-key";
        let data = b"audit-record";
        let mut out = [0u8; 32];
        let code = unsafe {
            ithute_rust_hmac_sha256(
                key.as_ptr(),
                key.len(),
                data.as_ptr(),
                data.len(),
                out.as_mut_ptr(),
            )
        };
        assert_eq!(code, 0);
        assert_eq!(out, hmac_sha256(key, data));
    }

    #[test]
    fn push_envelope_scan_rejects_binary_shape() {
        let valid = br#"{"type":"push","title":"hello"}"#;
        let mut out = PushEnvelopeScan::default();
        let code = unsafe { ithute_rust_push_envelope_scan(valid.as_ptr(), valid.len(), &mut out) };
        assert_eq!(code, 0);
        assert_eq!(out.utf8_valid, 1);
        assert_eq!(out.json_object_shape, 1);
        assert_eq!(out.nul_bytes, 0);

        let invalid = b"{\x00}";
        let code = unsafe { ithute_rust_push_envelope_scan(invalid.as_ptr(), invalid.len(), &mut out) };
        assert_eq!(code, 0);
        assert_eq!(out.nul_bytes, 1);
        assert_eq!(out.control_bytes, 1);
    }

    #[test]
    fn push_envelope_scan_bounds_payload() {
        let oversized = vec![b'a'; 64 * 1024 + 1];
        let mut out = PushEnvelopeScan::default();
        let code = unsafe { ithute_rust_push_envelope_scan(oversized.as_ptr(), oversized.len(), &mut out) };
        assert_eq!(code, 1);
    }

    #[test]
    fn empty_buffer_is_valid() {
        let mut out = ByteStats::default();
        let code = unsafe { ithute_rust_byte_stats(std::ptr::null(), 0, &mut out) };
        assert_eq!(code, 0);
        assert_eq!(out, ByteStats::default());
    }
}
