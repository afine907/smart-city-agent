"""
Tests for Logging Configuration module.
"""

import logging
import pytest

from traffic_agent.logging_config import (
    StructuredFormatter,
    get_logger,
    setup_logging,
)


class TestSetupLogging:
    """Test setup_logging function."""

    @pytest.fixture(autouse=True)
    def restore_root_logger(self):
        """Save and restore root logger state."""
        root = logging.getLogger()
        old_level = root.level
        old_handlers = root.handlers[:]
        yield
        root.setLevel(old_level)
        root.handlers = old_handlers

    def test_setup_simple(self):
        setup_logging(level="INFO", format_type="simple")
        logger = logging.getLogger("test")
        assert logger.level <= logging.INFO

    def test_setup_structured(self):
        setup_logging(level="DEBUG", format_type="structured")
        logger = logging.getLogger("test")
        assert logger.level <= logging.DEBUG

    def test_setup_with_file(self, tmp_path):
        log_file = str(tmp_path / "test.log")
        setup_logging(level="INFO", log_file=log_file)
        logger = logging.getLogger("test_file")
        logger.info("Test message")

        # Verify file was created
        assert (tmp_path / "test.log").exists()


class TestStructuredFormatter:
    """Test StructuredFormatter."""

    def test_format_basic(self):
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        formatted = formatter.format(record)
        assert "level=INFO" in formatted
        assert "logger=test" in formatted
        assert "message=Test message" in formatted

    def test_format_with_exception(self):
        formatter = StructuredFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="Error occurred",
            args=(),
            exc_info=exc_info,
        )
        formatted = formatter.format(record)
        assert "exception=" in formatted
        assert "ValueError" in formatted


class TestGetLogger:
    """Test get_logger function."""

    def test_get_logger(self):
        logger = get_logger("test_module", component="test")
        assert isinstance(logger, logging.LoggerAdapter)

    def test_logger_with_extra(self):
        logger = get_logger("test_extra", request_id="123")
        # Should not raise
        logger.info("Test message")
