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
    fn empty_buffer_is_valid() {
        let mut out = ByteStats::default();
        let code = unsafe { ithute_rust_byte_stats(std::ptr::null(), 0, &mut out) };
        assert_eq!(code, 0);
        assert_eq!(out, ByteStats::default());
    }
}
