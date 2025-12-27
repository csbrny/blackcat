from __future__ import annotations

from typing import List, Tuple

from .game import Card, card_points, card_rank, card_suit, RANK_VALUE


def choose_pass(hand: List[Card]) -> List[Card]:
    # Prefer passing high point cards.
    def sort_key(card: Card) -> Tuple[int, int]:
        return (card_points(card), RANK_VALUE[card_rank(card)])

    return sorted(hand, key=sort_key, reverse=True)[:3]


def choose_play(legal_moves: List[Card]) -> Card:
    # Prefer low point, low rank cards.
    def sort_key(card: Card) -> Tuple[int, int]:
        return (card_points(card), RANK_VALUE[card_rank(card)])

    return sorted(legal_moves, key=sort_key)[0]
