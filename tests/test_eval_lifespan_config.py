from __future__ import annotations

from unittest.mock import patch

import structlog.testing

from jordan_claw.config import Settings
from jordan_claw.main import _log_dropped_online_eval, configure_eval_defaults


@patch("jordan_claw.main.configure_online_evals")
@patch("jordan_claw.main.set_default_judge_model")
def test_configure_eval_defaults_wires_judge_model_and_online_sampling(
    mock_set_judge_model, mock_configure_online_evals
):
    """Lifespan wiring: judge model + online-eval sampling must be configured
    from Settings, with correlated sampling and a service-identifying tag so
    online-eval traces don't collapse into an unlabeled bucket."""
    settings = Settings.model_construct(
        eval_judge_model="anthropic:claude-sonnet-4-5-20250929",
        online_eval_sample_rate=0.25,
    )

    configure_eval_defaults(settings)

    mock_set_judge_model.assert_called_once_with("anthropic:claude-sonnet-4-5-20250929")
    mock_configure_online_evals.assert_called_once_with(
        default_sample_rate=0.25,
        sampling_mode="correlated",
        metadata={"service": "jordan-claw"},
        on_max_concurrency=_log_dropped_online_eval,
    )


@patch("jordan_claw.main.configure_online_evals")
@patch("jordan_claw.main.set_default_judge_model")
def test_configure_eval_defaults_defaults_sample_rate_to_zero(
    mock_set_judge_model, mock_configure_online_evals
):
    """online_eval_sample_rate=0.0 (the Settings default) must reach
    configure_online_evals unchanged: judge sampling off by default."""
    settings = Settings.model_construct(
        eval_judge_model="anthropic:claude-sonnet-4-5-20250929",
        online_eval_sample_rate=0.0,
    )

    configure_eval_defaults(settings)

    assert mock_configure_online_evals.call_args.kwargs["default_sample_rate"] == 0.0


def test_log_dropped_online_eval_logs_visibly():
    """A dropped online evaluation (process-wide concurrency limit hit) must
    not be silent: it's wired as `on_max_concurrency` in
    `configure_eval_defaults` precisely so a saturated pipeline is visible."""
    with structlog.testing.capture_logs() as cap_logs:
        _log_dropped_online_eval(ctx=None)

    assert any(entry["event"] == "online_eval_dropped_max_concurrency" for entry in cap_logs)
