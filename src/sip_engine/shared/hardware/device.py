"""Map detected GPU type to XGBoost device kwargs.

Centralises device configuration so the trainer and benchmark modules
don't embed device logic.
"""

from __future__ import annotations


def get_xgb_device_kwargs(device_type: str) -> dict:
    """Return XGBoost constructor kwargs for the given device type.

    Args:
        device_type: One of 'cuda', 'rocm', 'cpu', 'metal'.

    Returns:
        Dict suitable for ``**unpacking`` into :class:`xgboost.XGBClassifier`.

    Examples:
        >>> get_xgb_device_kwargs('cuda')
        {'device': 'cuda', 'tree_method': 'hist'}
        >>> get_xgb_device_kwargs('cpu')
        {'tree_method': 'hist'}
    """
    if device_type == "cuda":
        return {"device": "cuda", "tree_method": "hist"}

    if device_type == "rocm":
        # ROCm uses the CUDA HIP API in XGBoost
        return {"device": "cuda:0", "tree_method": "hist"}

    # 'cpu' and 'metal' — Metal has no XGBoost support
    return {"tree_method": "hist"}
