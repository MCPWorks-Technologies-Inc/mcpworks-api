"""Unit tests for metrics middleware."""

from unittest.mock import MagicMock, patch


class TestSetupMetrics:
    """Tests for setup_metrics function."""

    def test_setup_metrics_creates_instrumentator(self):
        """Test that setup_metrics creates an Instrumentator."""
        mock_app = MagicMock()

        with patch("mcpworks_api.middleware.metrics.Instrumentator") as mock_instrumentator_class:
            mock_instrumentator = MagicMock()
            mock_instrumentator.instrument.return_value = mock_instrumentator
            mock_instrumentator_class.return_value = mock_instrumentator

            from mcpworks_api.middleware.metrics import setup_metrics

            setup_metrics(mock_app)

            # Verify instrumentator was created
            mock_instrumentator_class.assert_called_once()

    def test_setup_metrics_instruments_app(self):
        """Test that setup_metrics instruments the app."""
        mock_app = MagicMock()

        with patch("mcpworks_api.middleware.metrics.Instrumentator") as mock_instrumentator_class:
            mock_instrumentator = MagicMock()
            mock_instrumentator.instrument.return_value = mock_instrumentator
            mock_instrumentator_class.return_value = mock_instrumentator

            from mcpworks_api.middleware.metrics import setup_metrics

            setup_metrics(mock_app)

            mock_instrumentator.instrument.assert_called_once_with(mock_app)

    def test_setup_metrics_exposes_endpoint(self):
        """Test that setup_metrics exposes /metrics endpoint."""
        mock_app = MagicMock()

        with patch("mcpworks_api.middleware.metrics.Instrumentator") as mock_instrumentator_class:
            mock_instrumentator = MagicMock()
            mock_instrumentator.instrument.return_value = mock_instrumentator
            mock_instrumentator_class.return_value = mock_instrumentator

            from mcpworks_api.middleware.metrics import setup_metrics

            setup_metrics(mock_app)

            mock_instrumentator.expose.assert_called_once_with(
                mock_app, endpoint="/metrics", include_in_schema=False
            )

    def test_setup_metrics_excludes_health_endpoints(self):
        """Test that health/metrics endpoints are excluded."""
        mock_app = MagicMock()

        with patch("mcpworks_api.middleware.metrics.Instrumentator") as mock_instrumentator_class:
            mock_instrumentator = MagicMock()
            mock_instrumentator.instrument.return_value = mock_instrumentator
            mock_instrumentator_class.return_value = mock_instrumentator

            from mcpworks_api.middleware.metrics import setup_metrics

            setup_metrics(mock_app)

            # Check the excluded_handlers parameter
            call_kwargs = mock_instrumentator_class.call_args[1]
            excluded = call_kwargs["excluded_handlers"]
            assert "/metrics" in excluded
            assert "/health" in excluded
            assert "/health/live" in excluded
            assert "/health/ready" in excluded

    def test_setup_metrics_configures_inprogress(self):
        """Test that in-progress tracking is configured."""
        mock_app = MagicMock()

        with patch("mcpworks_api.middleware.metrics.Instrumentator") as mock_instrumentator_class:
            mock_instrumentator = MagicMock()
            mock_instrumentator.instrument.return_value = mock_instrumentator
            mock_instrumentator_class.return_value = mock_instrumentator

            from mcpworks_api.middleware.metrics import setup_metrics

            setup_metrics(mock_app)

            call_kwargs = mock_instrumentator_class.call_args[1]
            assert call_kwargs["should_instrument_requests_inprogress"] is True
            assert call_kwargs["inprogress_name"] == "http_requests_inprogress"
            assert call_kwargs["inprogress_labels"] is True

    def test_setup_metrics_respects_env_var(self):
        """Test that env var configuration is enabled."""
        mock_app = MagicMock()

        with patch("mcpworks_api.middleware.metrics.Instrumentator") as mock_instrumentator_class:
            mock_instrumentator = MagicMock()
            mock_instrumentator.instrument.return_value = mock_instrumentator
            mock_instrumentator_class.return_value = mock_instrumentator

            from mcpworks_api.middleware.metrics import setup_metrics

            setup_metrics(mock_app)

            call_kwargs = mock_instrumentator_class.call_args[1]
            assert call_kwargs["should_respect_env_var"] is True

    def test_setup_metrics_does_not_group_status_codes(self):
        """Test that status codes are not grouped (e.g., 2xx)."""
        mock_app = MagicMock()

        with patch("mcpworks_api.middleware.metrics.Instrumentator") as mock_instrumentator_class:
            mock_instrumentator = MagicMock()
            mock_instrumentator.instrument.return_value = mock_instrumentator
            mock_instrumentator_class.return_value = mock_instrumentator

            from mcpworks_api.middleware.metrics import setup_metrics

            setup_metrics(mock_app)

            call_kwargs = mock_instrumentator_class.call_args[1]
            assert call_kwargs["should_group_status_codes"] is False

    def test_setup_metrics_ignores_untemplated(self):
        """Test that untemplated routes are ignored."""
        mock_app = MagicMock()

        with patch("mcpworks_api.middleware.metrics.Instrumentator") as mock_instrumentator_class:
            mock_instrumentator = MagicMock()
            mock_instrumentator.instrument.return_value = mock_instrumentator
            mock_instrumentator_class.return_value = mock_instrumentator

            from mcpworks_api.middleware.metrics import setup_metrics

            setup_metrics(mock_app)

            call_kwargs = mock_instrumentator_class.call_args[1]
            assert call_kwargs["should_ignore_untemplated"] is True

    def test_setup_metrics_returns_instrumentator(self):
        """Test that setup_metrics returns the instrumentator."""
        mock_app = MagicMock()

        with patch("mcpworks_api.middleware.metrics.Instrumentator") as mock_instrumentator_class:
            mock_instrumentator = MagicMock()
            mock_instrumentator.instrument.return_value = mock_instrumentator
            mock_instrumentator_class.return_value = mock_instrumentator

            from mcpworks_api.middleware.metrics import setup_metrics

            result = setup_metrics(mock_app)

            assert result == mock_instrumentator
