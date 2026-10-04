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
    fn empty_buffer_is_valid() {
        let mut out = ByteStats::default();
        let code = unsafe { ithute_rust_byte_stats(std::ptr::null(), 0, &mut out) };
        assert_eq!(code, 0);
        assert_eq!(out, ByteStats::default());
    }
}
