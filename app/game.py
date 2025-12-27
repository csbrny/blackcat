from __future__ import annotations

from dataclasses import dataclass, field
import random
from typing import Dict, List, Optional, Tuple

Card = str  # Format: <rank><suit>, e.g. "2C", "QH"

SUITS = ["C", "D", "S", "H"]
RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K", "A"]
RANK_VALUE = {rank: i for i, rank in enumerate(RANKS)}

PASS_LEFT = 0
PASS_RIGHT = 1
PASS_ACROSS = 2
PASS_HOLD = 3


@dataclass
class PlayerState:
    id: str
    name: str
    is_bot: bool = False


@dataclass
class GameState:
    players: List[PlayerState]
    scores: Dict[str, int] = field(default_factory=dict)
    hands: Dict[str, List[Card]] = field(default_factory=dict)
    hearts_broken: bool = False
    trick: List[Tuple[str, Card]] = field(default_factory=list)
    last_trick: List[Tuple[str, Card]] = field(default_factory=list)
    current_turn: Optional[str] = None
    round_index: int = 0
    trick_index: int = 0
    phase: str = "lobby"  # lobby, passing, playing, round_end, game_over
    pass_dir: int = PASS_LEFT
    pending_pass: Dict[str, List[Card]] = field(default_factory=dict)
    taken_points_round: Dict[str, int] = field(default_factory=dict)
    winner_id: Optional[str] = None

    def player_order(self) -> List[str]:
        return [p.id for p in self.players]


def make_deck() -> List[Card]:
    return [rank + suit for suit in SUITS for rank in RANKS]


def card_suit(card: Card) -> str:
    return card[1]


def card_rank(card: Card) -> str:
    return card[0]


def card_points(card: Card) -> int:
    if card_suit(card) == "H":
        return 1
    if card == "QS":
        return 13
    return 0


def is_point_card(card: Card) -> bool:
    return card_points(card) > 0


def deal_hands(players: List[PlayerState]) -> Dict[str, List[Card]]:
    deck = make_deck()
    random.shuffle(deck)
    hands = {p.id: [] for p in players}
    for i, card in enumerate(deck):
        hands[players[i % len(players)].id].append(card)
    for hand in hands.values():
        hand.sort(key=lambda c: (SUITS.index(card_suit(c)), RANK_VALUE[card_rank(c)]))
    return hands


def find_two_clubs_player(hands: Dict[str, List[Card]]) -> Optional[str]:
    for pid, hand in hands.items():
        if "2C" in hand:
            return pid
    return None


def trick_winner(trick: List[Tuple[str, Card]]) -> str:
    lead_suit = card_suit(trick[0][1])
    winning = trick[0]
    for pid, card in trick[1:]:
        if card_suit(card) != lead_suit:
            continue
        if RANK_VALUE[card_rank(card)] > RANK_VALUE[card_rank(winning[1])]:
            winning = (pid, card)
    return winning[0]


def pass_map(players: List[PlayerState], direction: int) -> Dict[str, str]:
    order = [p.id for p in players]
    size = len(order)
    mapping = {}
    for idx, pid in enumerate(order):
        if direction == PASS_LEFT:
            target = order[(idx + 1) % size]
        elif direction == PASS_RIGHT:
            target = order[(idx - 1) % size]
        elif direction == PASS_ACROSS:
            target = order[(idx + 2) % size]
        else:
            target = pid
        mapping[pid] = target
    return mapping


def legal_moves(
    hand: List[Card],
    trick: List[Tuple[str, Card]],
    hearts_broken: bool,
    is_first_trick: bool,
) -> List[Card]:
    if not hand:
        return []

    if not trick:
        if is_first_trick:
            return ["2C"] if "2C" in hand else [hand[0]]

        if hearts_broken:
            return list(hand)

        non_hearts = [c for c in hand if card_suit(c) != "H"]
        return non_hearts if non_hearts else list(hand)

    lead_suit = card_suit(trick[0][1])
    suited = [c for c in hand if card_suit(c) == lead_suit]
    if suited:
        return suited

    if is_first_trick:
        non_points = [c for c in hand if not is_point_card(c)]
        return non_points if non_points else list(hand)

    return list(hand)


class HeartsGame:
    def __init__(self, players: List[PlayerState]):
        self.state = GameState(players=players)
        self.state.scores = {p.id: 0 for p in players}

    def start_round(self) -> None:
        self.state.hands = deal_hands(self.state.players)
        self.state.trick = []
        self.state.last_trick = []
        self.state.hearts_broken = False
        self.state.trick_index = 0
        self.state.pending_pass = {}
        self.state.taken_points_round = {p.id: 0 for p in self.state.players}
        self.state.pass_dir = self.state.round_index % 4

        if self.state.pass_dir == PASS_HOLD:
            self.state.phase = "playing"
            self.state.current_turn = find_two_clubs_player(self.state.hands)
        else:
            self.state.phase = "passing"
            self.state.current_turn = None

    def submit_pass(self, player_id: str, cards: List[Card]) -> bool:
        if self.state.phase != "passing":
            return False
        if len(cards) != 3:
            return False
        hand = self.state.hands.get(player_id, [])
        if any(card not in hand for card in cards):
            return False

        self.state.pending_pass[player_id] = cards
        if len(self.state.pending_pass) < len(self.state.players):
            return True

        mapping = pass_map(self.state.players, self.state.pass_dir)
        for pid, pass_cards in self.state.pending_pass.items():
            for card in pass_cards:
                self.state.hands[pid].remove(card)

        for pid, pass_cards in self.state.pending_pass.items():
            target = mapping[pid]
            self.state.hands[target].extend(pass_cards)

        for hand in self.state.hands.values():
            hand.sort(key=lambda c: (SUITS.index(card_suit(c)), RANK_VALUE[card_rank(c)]))

        self.state.pending_pass = {}
        self.state.phase = "playing"
        self.state.current_turn = find_two_clubs_player(self.state.hands)
        return True

    def play_card(self, player_id: str, card: Card) -> bool:
        if self.state.phase != "playing":
            return False
        if self.state.current_turn != player_id:
            return False
        hand = self.state.hands.get(player_id, [])
        if card not in hand:
            return False

        is_first_trick = self.state.trick_index == 0
        legal = legal_moves(hand, self.state.trick, self.state.hearts_broken, is_first_trick)
        if card not in legal:
            return False

        if not self.state.trick:
            self.state.last_trick = []

        hand.remove(card)
        self.state.trick.append((player_id, card))
        if card_suit(card) == "H":
            self.state.hearts_broken = True

        if len(self.state.trick) < len(self.state.players):
            self.state.current_turn = self.next_player(player_id)
            return True

        winner = trick_winner(self.state.trick)
        points = sum(card_points(c) for _, c in self.state.trick)
        self.state.taken_points_round[winner] += points
        self.state.last_trick = list(self.state.trick)
        self.state.trick = []
        self.state.current_turn = winner

        if all(len(h) == 0 for h in self.state.hands.values()):
            self.finish_round()
        else:
            self.state.trick_index += 1
        return True

    def next_player(self, player_id: str) -> str:
        order = self.state.player_order()
        idx = order.index(player_id)
        return order[(idx + 1) % len(order)]

    def finish_round(self) -> None:
        self.state.phase = "round_end"
        moon_shooter = None
        for pid, points in self.state.taken_points_round.items():
            if points == 26:
                moon_shooter = pid
                break

        if moon_shooter:
            for pid in self.state.scores:
                if pid == moon_shooter:
                    continue
                self.state.scores[pid] += 26
        else:
            for pid, points in self.state.taken_points_round.items():
                self.state.scores[pid] += points

        self.state.round_index += 1
        if max(self.state.scores.values(), default=0) >= 100:
            self.state.phase = "game_over"
            self.state.winner_id = min(self.state.scores, key=self.state.scores.get)

    def start_next_round(self) -> bool:
        if self.state.phase != "round_end":
            return False
        self.start_round()
        return True

    def get_legal_moves(self, player_id: str) -> List[Card]:
        hand = self.state.hands.get(player_id, [])
        is_first_trick = self.state.trick_index == 0
        return legal_moves(hand, self.state.trick, self.state.hearts_broken, is_first_trick)
