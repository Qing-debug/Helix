import asyncio
import time

async def coroutine_example2():
    await asyncio.sleep(2)
    return "coroutine2 done"
async def coroutine_example1():
    await asyncio.sleep(4)
    return "coroutine1 done"


async def main1():
    loop = asyncio.get_running_loop()

    # Example 1: Direct coroutine await (sequential)
    print("result1 executing" )
    result1 = await coroutine_example1()
    print(result1)
    print("result2 executing" )
    result2 = await coroutine_example2()
    print(result2)

async def main2():
    loop = asyncio.get_running_loop()
    # Example 2: Task (concurrent with other tasks)
    print("Starting task...")
    task1 = asyncio.create_task(coroutine_example1())
    task2 = asyncio.create_task(coroutine_example2())
    # Event loop can do other work while task runs
    print("result1 executing")
    result1 = await task1
    print(result1)
    print("result2 executing")
    result2 = await task2
    print(result2)

asyncio.run(main2())


# async def set_result_later(fut):
#     await asyncio.sleep(1)
#     fut.set_result("Future resolved!")
#     # This coroutine returns None (no explicit return)
#
#
# async def main():
#     loop = asyncio.get_running_loop()
#     fut = loop.create_future()
#
#     asyncio.create_task(set_result_later(fut))  # Schedules the coroutine
#
#     # At this point, the Task is running in the background
#     # It will sleep for 1 second, then call fut.set_result(...)
#
#     result = await fut  # This waits for 'fut' to be resolved
#     # When the Task sets the result, this returns
#     # The value comes from the Future, NOT from the coroutine's return value
#     print(result)  # Prints "Future resolved!"
#
# asyncio.run(main())



# def inner():
#     yield 1
#     yield 2
#     # Falls off the end - raises StopIteration(None)
#
# def outer():
#     result = yield from inner()
#     print(f"Result: {result}")  # Result: None
#     yield 3
#
# gen = outer()
# print(next(gen))
# print(next(gen))
# print(next(gen))



# test_gen = test()
# print(next(test_gen))
# test_gen.throw(Exception("Test Exception"))

# gen1 = obj1()
# gen2 = obj2()
# print(next(gen1))
# print(next(gen2))
# print(next(gen1))
# print(next(gen2))






# async def fetch_data(id, sleep_time):
#     print(f"[{time.time():.1f}] Fetching data for ID: {id}")
#     await asyncio.sleep(sleep_time)
#     print(f"[{time.time():.1f}] COMPLETED ID: {id}")
#     return f"Data for ID: {id}"
#
#
# async def main():
#     start = time.time()
#     task1 = asyncio.create_task(fetch_data(1, 6))
#     task2 = asyncio.create_task(fetch_data(2, 3))
#
#     print(f"[{time.time():.1f}] Main waiting for task1...")
#     results1 = await task1
#     print(f"[{time.time():.1f}] Main got task1, now getting task2...")
#     results2 = await task2
#     print(f"[{time.time():.1f}] {results1}, {results2}")
#
#     return "hi"
#
# asyncio.run(main())
#
# print("hello")


# import asyncio
#
# async def fetch_data(id, sleep_time):
#     print(f"Fetching data for ID: {id}")
#     await asyncio.sleep(sleep_time)  # Simulate an I/O-bound operation
#     return f"Data for ID: {id}"
#
# async def main():
#     task1 = asyncio.create_task(fetch_data(1, 6))
#     task2 = asyncio.create_task(fetch_data(2, 3))
#     # task3 = asyncio.create_task(fetch_data(3, ))
#
#     results1 = await task1
#     results2 = await task2
#
#
#     print(results1, results2)
#
# asyncio.run(main())
