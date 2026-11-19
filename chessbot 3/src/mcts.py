"""D's Monte-Carlo Tree Search integrated with ChessMind's Engine contract.

The original choose_move(board, time_limit, rollout_limit, c) remains usable
and still returns a python-chess Move.  The MCTS class is the integration
adapter for C's build_engine("MCTS"), returning the required five fields.

IMPORTANT: `nodes` counts MCTS simulations (not alpha-beta nodes).  `score`
is a root-side win-rate proxy in [-100,100], not a material evaluation.
"""
from __future__ import annotations

import math
import random
import time

import chess

from .evaluate import evaluate


class Node:
    def __init__(self, board: chess.Board, move=None, parent=None, player_just_moved=None):
        # Preserve move history for threefold repetition/50-move claims.
        self.board = board.copy(stack=True)
        self.move = move
        self.parent = parent
        self.children = []
        self.visits = 0
        self.wins = 0.0  # rewards in [0,1] from player_just_moved viewpoint
        self.untried_moves = list(self.board.legal_moves)
        self.player_just_moved = player_just_moved
        self.depth = 0 if parent is None else parent.depth + 1

    def init(self, board: chess.Board, move=None, parent=None, player_just_moved=None):
        self.__init__(board, move=move, parent=parent,
                      player_just_moved=player_just_moved)


def _ucb1(child: Node, parent_visits: int, c: float) -> float:
    if child.visits == 0:
        return float("inf")
    return (child.wins / child.visits
            + c * math.sqrt(math.log(max(1, parent_visits)) / child.visits))


def _select(node: Node, c: float) -> Node:
    while node.children and not node.board.is_game_over(claim_draw=True) and not node.untried_moves:
        node = max(node.children, key=lambda child: _ucb1(child, node.visits, c))
    return node


def _expand(node: Node) -> Node:
    if not node.untried_moves:
        return node
    move = node.untried_moves.pop(random.randrange(len(node.untried_moves)))
    next_board = node.board.copy(stack=True)
    next_board.push(move)
    child = Node(next_board, move=move, parent=node,
                 player_just_moved=not next_board.turn)
    node.children.append(child)
    return child


def _terminal_score(board: chess.Board, root_player: bool) -> float:
    """A result from the root player's view: win=+1, draw=0, loss=-1."""
    outcome = board.outcome(claim_draw=True)
    if outcome is None or outcome.winner is None:
        return 0.0
    return 1.0 if outcome.winner == root_player else -1.0


def _truncated_score(board: chess.Board, root_player: bool) -> float:
    """Preserve D's evaluation-based rollout heuristic and score scale."""
    score = evaluate(board)  # side-to-move perspective
    root_score = score if board.turn == root_player else -score
    return max(-1.0, min(1.0, root_score / 100000.0))


def _rollout(board: chess.Board, root_player: bool, rollout_limit: int) -> float:
    sim_board = board.copy(stack=True)
    for _ in range(max(0, rollout_limit)):
        if sim_board.is_game_over(claim_draw=True):
            return _terminal_score(sim_board, root_player)
        moves = list(sim_board.legal_moves)
        if not moves:
            return _terminal_score(sim_board, root_player)
        sim_board.push(random.choice(moves))
    if sim_board.is_game_over(claim_draw=True):
        return _terminal_score(sim_board, root_player)
    return _truncated_score(sim_board, root_player)


def _backpropagate(node: Node, result: float, root_player: bool) -> None:
    """Convert [-1,1] root-view outcomes into [0,1] player-view rewards.

    D's original `1.0-result` was outside [0,1] for losses (result=-1).
    That distorted UCB1; use (1 +/- result)/2 instead.
    """
    root_reward = (1.0 + max(-1.0, min(1.0, result))) / 2.0
    current = node
    while current is not None:
        current.visits += 1
        reward = (1.0 - root_reward if current.player_just_moved is not None
                  and current.player_just_moved != root_player else root_reward)
        current.wins += reward
        current = current.parent


def _search(board: chess.Board, *, time_limit: float, rollout_limit: int,
            c: float, simulations: int | None = None):
    if board.is_game_over(claim_draw=True):
        raise ValueError("cannot choose move for finished game")
    legal_moves = list(board.legal_moves)
    if not legal_moves:
        raise ValueError("no legal moves available")
    root = Node(board, player_just_moved=None)
    root_player = board.turn
    deadline = time.perf_counter() + max(0.0, float(time_limit))
    iterations = 0
    max_depth = 0
    while (time.perf_counter() < deadline
           and (simulations is None or iterations < simulations)):
        node = _select(root, c)
        if not node.board.is_game_over(claim_draw=True) and node.untried_moves:
            node = _expand(node)
        result = _rollout(node.board, root_player, rollout_limit)
        _backpropagate(node, result, root_player)
        iterations += 1
        max_depth = max(max_depth, node.depth)
    if not root.children:
        # The calling game can still make progress if a zero time budget was given.
        return random.choice(legal_moves), iterations, max_depth, 0
    best = max(root.children, key=lambda child: child.visits)
    estimated_score = int(round(100 * (2 * best.wins / best.visits - 1)))
    return best.move, iterations, max_depth, estimated_score


def choose_move(board: chess.Board, time_limit: float = 3.0,
                rollout_limit: int = 20, c: float = 1.41) -> chess.Move:
    """D's public function API: return a legal chess.Move without mutation."""
    return _search(board, time_limit=time_limit, rollout_limit=rollout_limit, c=c)[0]


class MCTS:
    """Bridge D's MCTS to C's five-field Engine.choose() API."""
    def __init__(self, simulations: int = 2000, time_limit_ms: int = 1500,
                 rollout_depth: int = 20, c: float = 1.41):
        if not isinstance(simulations, int) or simulations < 1:
            raise ValueError("simulations must be a positive integer")
        if time_limit_ms <= 0 or rollout_depth < 0 or c <= 0:
            raise ValueError("invalid MCTS configuration")
        self.simulations = simulations
        self.time_limit_ms = time_limit_ms
        self.rollout_depth = rollout_depth
        self.c = c

    def choose(self, board: chess.Board, time_limit: float | None = None) -> dict:
        budget = self.time_limit_ms / 1000.0 if time_limit is None else float(time_limit)
        if budget < 0:
            raise ValueError("time_limit must be nonnegative")
        t0 = time.perf_counter()
        move, nodes, depth, score = _search(
            board, time_limit=budget, rollout_limit=self.rollout_depth,
            c=self.c, simulations=self.simulations)
        return {"move": move.uci(), "score": score, "depth": depth,
                "nodes": nodes, "ms": max(0, int((time.perf_counter() - t0) * 1000))}
