import discord

class Pages:
    """
    A base class for handling paginated objects.

    Parameters:
    - items: Any[Iterable]
        The items to be partitioned and paginated, can be any iterable
    - per_page: int
        The number of items to be included on each page
        Default: 1
    - use_embed: bool
        Whether the items should be returned as a uniform embed
        Default: False
    - joiner: str
        The string that will be used to join items on a page
        Default: '\n'

    Attributes:
    - pages
        Returns all pages
    """
    def __init__(
            self,
            items,
            /, per_page: int = 1,
            *, use_embed: bool = False,
            joiner: str = '\n'):
        self.items = items
        self.joiner = joiner
        self.per_page = per_page
        self.use_embed = use_embed
        self.paginator = None

    def __repr__(self):
        return '<{0.__class__.__name__} pages={1}>'.format(self, len(self.pages))

    def link(self, paginator):
        self.paginator = paginator

    def _split_pages(self):
        _items = self.items
        _pages = []
        while _items:
            _pages.append(tuple(_items[:self.per_page]))
            _items = _items[self.per_page:]
        return _pages

    @property
    def pages(self):
        return self._split_pages()

    def __getitem__(self, index):
        content = self.joiner.join(self.pages[index])
        if self.use_embed:
            return discord.Embed(description=content)
        return content

    def append(self, new):
        self.items.append(new)
        if self.paginator:
            self.paginator.dispatch_update()

    def prepend(self, new):
        self.items.insert(0, new)
        if self.paginator:
            self.paginator.dispatch_update()

    def __len__(self):
        return len(self.pages)

class EmbedPages(Pages):
    """
    A subclass of Pages that takes an iterable of Embeds as its input.
    """
    def __init__(self, items):
        super().__init__(items, 1)

    @property
    def pages(self):
        return self.items