import time
import random
from collections import deque

import matplotlib.pyplot as plt


# ==========================================================
# USER COMFORT THRESHOLD
# ==========================================================

COMFORT_TIME = 0.1


# ==========================================================
# SETTINGS
# ==========================================================

HAND_SIZE = 10

OPERATIONS_PER_TURN = 200

REPEATS = 200


# Основной диапазон
deck_sizes = [
    100,
    500,
    1000,
    2500,
    5000,
    10000,
    15000,
    20000,
    25000,
    30000,
]


# Для детального графика
small_deck_sizes_limit = 2500


# ==========================================================
# LIST IMPLEMENTATION
# ==========================================================


class ListDeck:
    def __init__(self, cards):
        self.cards = cards

    def draw(self, n):

        drawn = self.cards[:n]

        self.cards = self.cards[n:]

        return drawn

    def add_cards(self, cards):

        self.cards.extend(cards)

    def shuffle(self):

        random.shuffle(self.cards)

    def size(self):

        return len(self.cards)


# ==========================================================
# DEQUE IMPLEMENTATION
# ==========================================================


class DequeDeck:
    def __init__(self, cards):

        self.cards = deque(cards)

    def draw(self, n):

        drawn = []

        for _ in range(n):
            drawn.append(self.cards.popleft())

        return drawn

    def add_cards(self, cards):

        self.cards.extend(cards)

    def shuffle(self):

        temp = list(self.cards)

        random.shuffle(temp)

        self.cards = deque(temp)

    def size(self):

        return len(self.cards)


# ==========================================================
# HEAVY TURN SIMULATION
# ==========================================================


def simulate_turn(deck_class, deck_size, with_shuffle):

    draw_deck = deck_class(list(range(deck_size)))

    discard_deck = deck_class([])

    start = time.perf_counter()

    for _ in range(OPERATIONS_PER_TURN):
        if draw_deck.size() < HAND_SIZE:
            if with_shuffle:
                discard_cards = discard_deck.draw(discard_deck.size())

                draw_deck.add_cards(discard_cards)

                draw_deck.shuffle()

        if draw_deck.size() >= HAND_SIZE:
            hand = draw_deck.draw(HAND_SIZE)

            discard_deck.add_cards(hand)

    end = time.perf_counter()

    return end - start


# ==========================================================
# RESULTS
# ==========================================================

list_no_shuffle = []
list_shuffle = []

deque_no_shuffle = []
deque_shuffle = []


# ==========================================================
# BENCHMARK
# ==========================================================

for size in deck_sizes:
    print(f"Testing deck size: {size}")

    # ------------------------------------------------------
    # LIST WITHOUT SHUFFLE
    # ------------------------------------------------------

    total = 0

    for _ in range(REPEATS):
        total += simulate_turn(ListDeck, size, False)

    list_no_shuffle.append(total / REPEATS)

    # ------------------------------------------------------
    # LIST WITH SHUFFLE
    # ------------------------------------------------------

    total = 0

    for _ in range(REPEATS):
        total += simulate_turn(ListDeck, size, True)

    list_shuffle.append(total / REPEATS)

    # ------------------------------------------------------
    # DEQUE WITHOUT SHUFFLE
    # ------------------------------------------------------

    total = 0

    for _ in range(REPEATS):
        total += simulate_turn(DequeDeck, size, False)

    deque_no_shuffle.append(total / REPEATS)

    # ------------------------------------------------------
    # DEQUE WITH SHUFFLE
    # ------------------------------------------------------

    total = 0

    for _ in range(REPEATS):
        total += simulate_turn(DequeDeck, size, True)

    deque_shuffle.append(total / REPEATS)


# ==========================================================
# MAIN GRAPH
# ==========================================================

plt.figure(figsize=(14, 8))

plt.plot(
    deck_sizes,
    list_no_shuffle,
    marker="o",
    linewidth=2,
)

plt.plot(
    deck_sizes,
    list_shuffle,
    marker="s",
    linewidth=2,
)

plt.plot(
    deck_sizes,
    deque_no_shuffle,
    marker="^",
    linewidth=2,
)

plt.plot(
    deck_sizes,
    deque_shuffle,
    marker="D",
    linewidth=2,
)

# Граница комфортного ожидания
plt.axhline(
    y=COMFORT_TIME,
    linestyle="--",
    linewidth=2,
)

plt.yscale("log")

plt.xlabel("Размер колоды")

plt.ylabel("Среднее время выполнения (сек, log scale)")

plt.title("Сравнение производительности list и deque")

plt.legend(
    [
        "List без перемешивания",
        "List с перемешиванием",
        "Deque без перемешивания",
        "Deque с перемешиванием",
        "Граница комфортного ожидания",
    ]
)

plt.grid(True)

plt.tight_layout()

plt.savefig("deck_performance_full.png", dpi=300)

plt.close()


# ==========================================================
# SMALL DECK GRAPH
# ==========================================================

small_indices = [
    i for i, size in enumerate(deck_sizes) if size <= small_deck_sizes_limit
]

small_sizes = [deck_sizes[i] for i in small_indices]

small_list_no_shuffle = [list_no_shuffle[i] for i in small_indices]

small_list_shuffle = [list_shuffle[i] for i in small_indices]

small_deque_no_shuffle = [deque_no_shuffle[i] for i in small_indices]

small_deque_shuffle = [deque_shuffle[i] for i in small_indices]


plt.figure(figsize=(14, 8))

plt.plot(
    small_sizes,
    small_list_no_shuffle,
    marker="o",
    linewidth=2,
)

plt.plot(
    small_sizes,
    small_list_shuffle,
    marker="s",
    linewidth=2,
)

plt.plot(
    small_sizes,
    small_deque_no_shuffle,
    marker="^",
    linewidth=2,
)

plt.plot(
    small_sizes,
    small_deque_shuffle,
    marker="D",
    linewidth=2,
)

plt.xlabel("Размер колоды")

plt.ylabel("Среднее время выполнения (сек)")

plt.title("Сравнение производительности list и deque (до 2500 карт)")

plt.legend(
    [
        "List без перемешивания",
        "List с перемешиванием",
        "Deque без перемешивания",
        "Deque с перемешиванием",
    ]
)

plt.grid(True)

plt.tight_layout()

plt.savefig("deck_performance_small.png", dpi=300)

plt.close()


# ==========================================================
# RESULTS
# ==========================================================

print()
print("Benchmark completed.")
print()

print("Saved graphs:")
print("- deck_performance_full.png")
print("- deck_performance_small.png")
