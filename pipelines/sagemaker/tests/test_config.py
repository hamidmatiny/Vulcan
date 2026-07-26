from vulcan_sagemaker.config import estimate_manual_smoke_cost


def test_cost_estimate_cpu_and_gpu() -> None:
    cpu = estimate_manual_smoke_cost(use_gpu=False)
    gpu = estimate_manual_smoke_cost(use_gpu=True)
    assert cpu.total_usd > 0
    assert gpu.total_usd > cpu.total_usd
    assert "ml.m5" in cpu.train_instance
    assert "ml.g4dn" in gpu.train_instance
