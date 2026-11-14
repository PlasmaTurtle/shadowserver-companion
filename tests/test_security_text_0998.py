"""Reusable text representation checks, separate from workflow media policies."""

import pytest

from workbench.aegis.errors import InputValidationError
from workbench.aegis.text import decode_bounded_text, parse_media_type


def decode(body, content_type="text/plain", **options):
    return decode_bounded_text(
        body,
        content_type,
        allowed_media={"text/plain", "application/json"},
        max_bytes=64,
        **options,
    )


def test_media_normalization_and_parameters_are_shared_without_workflow_policy():
    assert parse_media_type(' Application/JSON ; Charset="UTF-8"; profile=record') == (
        "application/json",
        {"charset": "UTF-8", "profile": "record"},
    )
    assert parse_media_type("image/png")[0] == "image/png"
    with pytest.raises(InputValidationError) as error:
        decode(b"image", "image/png")
    assert error.value.code == "unsupported_content"


@pytest.mark.parametrize(
    "value",
    [
        None,
        b"text/plain",
        "",
        "text",
        "text/plain\r\nContent-Length:4",
        "text/plain\x00",
        "text/plain; charset=utf-8; CHARSET=ascii",
        "text/plain; charset",
        "text/plain;",
        'text/plain; charset="utf-8',
        "text/plain; bad=has space",
        "text/plain; a=" + "a" * 512,
    ],
)
def test_invalid_or_ambiguous_media_is_rejected(value):
    with pytest.raises(InputValidationError) as error:
        parse_media_type(value)
    assert error.value.code == "unsupported_content"


@pytest.mark.parametrize(
    "body,media,expected",
    [
        (b"plain", "text/plain", "plain"),
        (b"\xef\xbb\xbf{}", "application/json; charset=UTF-8", "{}"),
        (b"caf\xe9", "text/plain; charset=iso-8859-1", "café"),
        (b"\x80 10", "text/plain; charset=windows-1252", "€ 10"),
        (b"ascii", "text/plain; charset=us-ascii", "ascii"),
    ],
)
def test_supported_explicit_encodings_decode_strictly(body, media, expected):
    assert decode(body, media) == expected


@pytest.mark.parametrize(
    "body,media,code",
    [
        (b"a" * 65, "text/plain", "invalid_response"),
        (bytearray(b"plain"), "text/plain", "invalid_response"),
        (b"\xff", "text/plain", "invalid_text"),
        (b"\xff", "text/plain; charset=ascii", "invalid_text"),
        (b"plain", "text/plain; charset=utf-16", "unsupported_charset"),
        (b"plain", "text/plain; charset=rot13", "unsupported_charset"),
        (b"MZbinary", "text/plain", "nontext_response"),
        (b"\xef\xbb\xbf \n%PDF-1.0", "text/plain", "nontext_response"),
        (b"PK\x03\x04archive", "text/plain", "nontext_response"),
        (b"a\x00b", "text/plain", "nontext_response"),
        (b"a\x1bb", "text/plain", "nontext_response"),
        (b"a\xc2\x85b", "text/plain", "nontext_response"),
    ],
)
def test_invalid_bytes_binary_formats_and_byte_limits_are_enforced(body, media, code):
    with pytest.raises(InputValidationError) as error:
        decode(body, media)
    assert error.value.code == code


def test_partial_decoding_only_tolerates_an_unfinished_final_codepoint():
    assert decode(b"valid\xe2\x82", partial=True) == "valid"
    with pytest.raises(InputValidationError) as error:
        decode(b"valid\xe2\x82")
    assert error.value.code == "invalid_text"
    with pytest.raises(InputValidationError):
        decode(b"bad\xffthen\xe2", partial=True)


def test_json_caller_can_require_utf8_without_changing_contact_encodings():
    assert decode(b"{}", "application/json", allowed_charsets={"utf-8", "utf8"}) == "{}"
    with pytest.raises(InputValidationError) as error:
        decode(b"{}", "application/json; charset=windows-1252", allowed_charsets={"utf-8", "utf8"})
    assert error.value.code == "unsupported_charset"


def test_invalid_limits_are_programmer_errors_not_permissive_fallbacks():
    for value in (0, -1, True, 2.5):
        with pytest.raises(ValueError):
            parse_media_type("text/plain", max_length=value)
        with pytest.raises(ValueError):
            decode_bounded_text(b"ok", "text/plain", allowed_media={"text/plain"}, max_bytes=value)
