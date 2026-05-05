# Student A - Alice
# HW1: Sorting Algorithms
# Approach: Simple conversion to int, sort, and output

nums = input().split()
nums = [int(n) for n in nums]
nums.sort()
print(" ".join(str(n) for n in nums))
