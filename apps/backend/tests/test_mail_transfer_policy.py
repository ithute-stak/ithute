from app.services.mail_transfer_policy import (
    FileDescriptor, TransferMode, choose_transfer_mode, MIB,
)


def test_small_file_uses_existing_mime_transport():
    result = choose_transfer_mode([FileDescriptor("invoice.pdf", 2 * MIB)])
    assert result.mode == TransferMode.INLINE


def test_over_ten_mib_routes_to_secure_delivery():
    result = choose_transfer_mode([FileDescriptor("archive.zip", 12 * MIB)])
    assert result.mode == TransferMode.SECURE_LINK


def test_aggregate_smtp_limit_routes_to_secure_delivery():
    result = choose_transfer_mode([
        FileDescriptor("a.pdf", 9 * MIB),
        FileDescriptor("b.pdf", 9 * MIB),
    ])
    assert result.mode == TransferMode.SECURE_LINK


def test_too_many_files_routes_to_secure_delivery():
    result = choose_transfer_mode([FileDescriptor(str(n), 1) for n in range(21)])
    assert result.mode == TransferMode.SECURE_LINK


def test_hard_limit_rejects_not_silently_truncates():
    result = choose_transfer_mode([FileDescriptor("huge.bin", 2049 * MIB)])
    assert result.mode == TransferMode.UNSUPPORTED
    assert result.reason == "per_file_hard_limit"


def test_empty_file_names_and_negative_sizes_are_invalid():
    assert choose_transfer_mode([FileDescriptor("", 1)]).mode == TransferMode.UNSUPPORTED
    assert choose_transfer_mode([FileDescriptor("bad", -1)]).mode == TransferMode.UNSUPPORTED


def test_empty_files_can_be_sent_without_transfer():
    assert choose_transfer_mode([]).mode == TransferMode.INLINE
