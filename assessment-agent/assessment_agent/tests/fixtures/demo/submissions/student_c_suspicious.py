import heapq
from typing import List, Optional
from functools import reduce

def merge_sort(arr: List[int]) -> List[int]:
    """Implements merge sort with O(n log n) time complexity."""
    if len(arr) <= 1:
        return arr
    mid = len(arr) // 2
    left = merge_sort(arr[:mid])
    right = merge_sort(arr[mid:])
    return _merge(left, right)

def _merge(left: List[int], right: List[int]) -> List[int]:
    """Merges two sorted arrays in O(n) time."""
    result = []
    i = j = 0
    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            result.append(left[i])
            i += 1
        else:
            result.append(right[j])
            j += 1
    result.extend(left[i:])
    result.extend(right[j:])
    return result

def validate_input(raw: str) -> Optional[List[int]]:
    """Validates and parses input string into integer list."""
    try:
        return [int(x) for x in raw.strip().split()]
    except ValueError:
        return None

if __name__ == "__main__":
    raw_input = input()
    numbers = validate_input(raw_input)
    if numbers is not None:
        sorted_numbers = merge_sort(numbers)
        print(" ".join(map(str, sorted_numbers)))
