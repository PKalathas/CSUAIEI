# HW1: Sorting Algorithms Report

## Approach

I implemented a simple sorting solution using Python's built-in `sort()` method.
The input is read as a string, split into individual elements, converted to integers,
sorted, and then printed as space-separated values.

## Time Complexity

The built-in Python sort uses Timsort, which has:
- **Best case**: O(n) when the input is already sorted
- **Average case**: O(n log n)
- **Worst case**: O(n log n)

This is optimal for a comparison-based sort.

## Space Complexity

Timsort uses O(n) additional space for the merge operations.

## Testing

I tested my solution with:
- Basic unsorted input: `3 1 2` → `1 2 3` ✓
- Already sorted: `1 2 3 4 5` → `1 2 3 4 5` ✓
- Negative numbers: `-3 1 -2 0 5` → `-3 -2 0 1 5` ✓
- Duplicates: `3 1 2 1 3` → `1 1 2 3 3` ✓

## Challenges

The main challenge was remembering to convert the string inputs to integers
before sorting. Without this conversion, Python sorts lexicographically which
gives incorrect results for multi-digit numbers.

## Conclusion

The solution correctly handles all edge cases including negative numbers,
duplicates, and single-element inputs. Using Python's built-in sort is
the most practical approach for this assignment.
