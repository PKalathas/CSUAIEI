# Student D - Diana
# HW1 sorting
# bubble sort from the lecture slides

def bubble_sort(arr):
    n = len(arr)
    for i in range(n):
        for j in range(0, n-i-1):
            if arr[j] > arr[j+1]:
                arr[j], arr[j+1] = arr[j+1], arr[j]
    return arr

data = input().split()
# forgot to convert to int here for some cases
try:
    data = [int(x) for x in data]
    result = bubble_sort(data)
    print(" ".join(str(x) for x in result))
except:
    print("error")
