# # import asyncio

# # async def greet():
# #     #print("BRO")
# #     return "Hello"

# # async def main():
# #     result = await greet()
    
# #     print("BROthis is bro")
# #     print(result)
# #     # await greet()

# # asyncio.run(main())

# # #main()
# # import time

# # def fetch_data(name):
# #     print(f"Fetching {name}...")
# #     time.sleep(2)
# #     print(f"Finished {name}")

# # start = time.perf_counter()

# # fetch_data("API 1")
# # fetch_data("API 2")

# # print(f"Total: {time.perf_counter() - start:.1f}s")



# import asyncio
# import time

# async def fetch_data(name):
#     print(f"Fetching {name}...")
#     await asyncio.sleep(2)
#     print(f"Finished {name}")

# async def main():
#     await asyncio.gather(
#         fetch_data("API 1"),
#         fetch_data("API 2")
#     )

# start = time.perf_counter()
# asyncio.run(main())
# print(f"Total: {time.perf_counter() - start:.1f}s")




