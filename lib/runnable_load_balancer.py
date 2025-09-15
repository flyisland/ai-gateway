import itertools
from typing import Iterator, override

from langchain_core.runnables import Runnable


class RunnableLoadBalancer(Runnable):
    """A runnable that performs a round-robin selection over a list of runnables."""

    def __init__(self, runnables: list[Runnable], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.runnables = runnables
        self.iterator: Iterator[Runnable] = itertools.cycle(runnables)

    @override
    def invoke(self, *args, **kwargs):
        return self.next_runnable().invoke(*args, **kwargs)

    @override
    def stream(self, *args, **kwargs):
        return self.next_runnable().stream(*args, **kwargs)

    @override
    async def ainvoke(self, *args, **kwargs):
        return await self.next_runnable().ainvoke(*args, **kwargs)

    @override
    async def astream(self, *args, **kwargs):
        return await self.next_runnable().astream(*args, **kwargs)

    def next_runnable(self):
        return next(self.iterator)
