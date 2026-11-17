from typing import List, Dict, Tuple
from fastapi import HTTPException, status

def calculate_equal_split(total_paise: int, participant_ids: List[str], host_id: str) -> Dict[str, int]:
    """
    Distributes total_paise among participants with exact integer paise precision.
    Remainder paise is deterministically assigned to the host, ensuring sum == total_paise.
    """
    n = len(participant_ids)
    if n == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Participant list cannot be empty")

    base_share = total_paise // n
    remainder = total_paise % n

    allocations: Dict[str, int] = {}
    for pid in participant_ids:
        allocations[pid] = base_share

    # Assign remainder paise to host if present, otherwise distribute sequentially
    if remainder > 0:
        if host_id in allocations:
            allocations[host_id] += remainder
        else:
            for i in range(remainder):
                allocations[participant_ids[i]] += 1

    assert sum(allocations.values()) == total_paise, "Integrity check: split sum must strictly equal total paise"
    return allocations

def validate_custom_split(total_paise: int, custom_shares: Dict[str, int], required_ids: List[str]) -> Dict[str, int]:
    """
    Validates that every required participant has a positive share and sum matches total_paise exactly.
    """
    missing = [pid for pid in required_ids if pid not in custom_shares]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing custom allocation for participant(s): {missing}"
        )

    for pid, amount in custom_shares.items():
        if amount <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Participant share must be greater than zero. Received: {amount} paise."
            )

    shares_sum = sum(custom_shares.values())
    if shares_sum != total_paise:
        diff = total_paise - shares_sum
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Custom shares sum (₹{shares_sum/100:.2f}) does not match order total (₹{total_paise/100:.2f}). Discrepancy: ₹{diff/100:.2f}"
        )

    return custom_shares

def redistribute_shares(total_paise: int, active_ids: List[str], host_id: str) -> Dict[str, int]:
    """
    Dynamic redistribution algorithm:
    Calculates revised equal shares strictly among the remaining active participants.
    """
    if not active_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot redistribute: no active participants remaining."
        )

    return calculate_equal_split(total_paise, active_ids, host_id)
