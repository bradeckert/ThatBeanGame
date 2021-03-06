from card import Card, Deck, Field
from player import Player
import uuid
import json
import asyncio
import util
from typing import List, Dict, Tuple
from trade import Trade, TradingCard
import constants


def check_stage(stages: Tuple[int, ...]):
    '''Verifies it's the right stage for an action'''
    def decorator(f):
        def wrapper(self, *args, **kwargs):
            if self.stage_index not in stages:
                return util.error('Invalid move')
            return f(self, *args, **kwargs)
        return wrapper
    return decorator

def check_turn(f):
    '''Verifys that it's the requesting player's turn'''
    def wrapper(self, *args, **kwargs):
        if args[0] != self.players[self.current_player_index]:
            return util.error('It is not your turn')
        return f(self, *args, **kwargs)
    return wrapper

def check_pending(f):
    '''
    Checks that a player has no cards in pending.
    NOTE: This must always follow a check_turn to verify that current player is requesting player
    '''
    def wrapper(self, *args, **kwargs):
        if self.players[self.current_player_index].pending_cards:
            return util.error('Must play pending cards first')
        return f(self, *args, **kwargs)
    return wrapper

class Game:
    def __init__(self, game_type: str) -> None:
        self.players: List[Player] = []
        self.deck: Deck = Deck()
        self.playthrough: int = 0
        self.discards: Deck = Deck()
        self.current_player_index: int = 0
        self.status: str = 'Awaiting'  # Awaiting, Running, Completed
        self.id: str = str(uuid.uuid4())[:6]
        self.stage_index: int = 0
        self.market: List[Card] = []
        self.trades: List[Trade] = []
        self.winner = None
        self.game_type: str = game_type
        self.last_updates: List[Dict] = []

        self.deck.build_deck()
        self.deck.shuffle()

    def add_player(self, player: Player) -> None:
        '''Adds new player to current game'''
        # First player is host
        if not self.players:
            player.is_host = True
        self.players.append(player)

    def leave_game(self, player: Player) -> Dict[str, str]:
        '''Removes player from game and progresses game if it's that players turn'''
        current_player = self.players[self.current_player_index]
        current_stage = self.stage_index
        if len(self.players) == 1:
            self.status = "Completed"
            return util.success("Successfully ended game")
        if player == current_player:
            next_player = self.players[(self.current_player_index + 1) % len(self.players)]
            self.players = [_player for _player in self.players if _player != player]
            self.current_player_index = self.players.index(next_player)
            self.stage_index = 0
        else:
            self.players = [_player for _player in self.players if _player != player]
            self.current_player_index = self.players.index(current_player)
        return util.success("Successfully left game")

    def is_full(self) -> bool:
        '''Checks if max players have been reached'''
        if len(self.players) < constants.MAX_PLAYERS:
            return False
        return True

    def start_game(self, player: Player) -> Dict[str, str]:
        '''Starts game by dealing cards to players and setting status'''
        if self.status != 'Awaiting':
            return util.error('Game has already started')
        if not player.is_host:
            return util.error('Only host can start game')
        self.deal_cards()
        self.status = 'Running'
        return util.success('Successfully started game')

    def retrieve_game(self, player: Player) -> Dict:
        return {
            'player_info': player.to_dict_private(),
            'players': [other_player.to_dict_public() for other_player in self.players if other_player != player],
            'deck_count': self.deck.get_length(),
            'playthrough': self.playthrough,
            'discard_count': self.discards.get_length(),
            'current_player': self.players[self.current_player_index].name,
            'status': self.status,
            'game_id': self.id,
            'stage': constants.STAGES[self.stage_index],
            'market': self.market_to_dict(),
            'trades': [trade.to_public_dict() for trade in self.trades],
            'game_type': self.game_type,
            'winner': self.winner
        }

    @check_stage((1, 2))
    @check_turn
    @check_pending
    def deck_to_market(self, player: Player) -> Dict[str, str]:
        '''Draws top 2 cards from deck and places them in market'''
        self.market += self.draw_cards(2)
        self.stage_index = 3
        return util.success('Cards drawn into market')

    @check_stage((3,))
    @check_turn
    @check_pending
    def deck_to_hand(self, player: Player) -> Dict[str, str]:
        '''Draws three cards from market to players hand'''
        if self.market:
            return util.error("Cannot draw cards until market is empty")
        player.hand = player.hand + self.draw_cards(3)
        self.go_next_stage()
        self.go_next_player()
        return util.success('Successfully drew two cards for hand')

    @check_stage((0,1))
    @check_turn
    @check_pending
    def hand_to_field(self, player: Player, field_index: int) -> Dict[str, str]:
        '''
        Plays card from users hand to field. No confirmation.
        '''
        result = self.verify_field(player, field_index)
        if result.get('error'):
            return result
        card: Card = player.hand[0]
        player.hand = player.hand[1:]
        return self.play_card(player, result['field'], card)

    @check_stage((3,))
    @check_turn
    @check_pending
    def market_to_field(self, player: Player, field_index: int, card_id: str) -> Dict[str, str]:
        ''' Plays card from market to field. No confirmation. '''
        result = self.verify_field(player, field_index)
        if result.get('error'):
            return result
        card: Card = self.pop_card_from_list(card_id, self.market)
        return self.play_card(player, result['field'], card)

    def pending_to_field(self, player: Player, field_index: int, card_id: str) -> Dict[str, str]:
        '''
        Plays card from pending to field. No confirmation.
        '''
        result = self.verify_field(player, field_index)
        if result.get('error'):
            return result
        card: Card = self.pop_card_from_list(card_id, player.pending_cards)
        return self.play_card(player, result['field'], card)
    
    def play_card(self, player: Player, field: Field, card: Card) -> Dict[str, str]:
        '''
        Plays card from anywhere
        '''
        # Add card to field, if fails, cash in and try again
        if not field.add_card(card):
            self.cash_in(field, player)
            if not field.add_card(card):
                return util.error("Cannot add card to field")

        # Move stage forward if playing from hand
        if self.stage_index in (0, 1):
            self.go_next_stage()   
        return util.success('Card successfully played')

    @check_stage((3,))
    def create_trade(self, p1: Player, p2_name: str, card_ids: List[str], wants: List[str]):
        tcs: List[TradingCard] = self.ids_to_tcs(p1, card_ids)
        new_trades: List[Trade] = []
        p2: Player = util.shrink([player for player in self.players if player.name == p2_name])
        if not p2:
            return util.error("Player chosen is not in game")
        new_trades += [Trade(p1, p2, tcs, wants)]
        self.trades += new_trades
        return util.success('Successfully created trade')

    def accept_trade(self, player: Player, trade_id: str, card_ids: List[str]):
        tcs: List[TradingCard] = self.ids_to_tcs(player, card_ids)
        trade: Trade = util.shrink([trade for trade in self.trades if trade.id == trade_id])
        if not trade:
            return util.error("Trade does not exist")
        if player is not trade.p2:
            return util.error("You are not in this trade")
        result = trade.accept(tcs)
        if not result.get('error'):
            self.trades = [trade for trade in self.trades if trade.id != trade_id]
        return result

    def reject_trade(self, player: Player, trade_id: str):
        trade: Trade = util.shrink([trade for trade in self.trades if trade.id == trade_id])
        if not trade:
            return util.error("Trade does not exist")
        if player is not trade.p2:
            return util.error("You are not in this trade")
        # Remove trade from trades
        self.trades = [trade for trade in self.trades if trade.id != trade_id]
        return util.success("Trade successfully rejected")

    def buy_field(self, player: Player):
        '''Buy third field for 3 coins'''
        if player.coins < 3:
            return util.error("Not enough coins to purchase third field")
        if player.fields[2].enabled:
            return util.error("Field already purchased")
        player.coins -= 3
        player.fields[2].enabled = True
        return util.success("Successfully purchased third field")
        
    def go_next_stage(self) -> None:
        self.stage_index = (self.stage_index + 1) % len(constants.STAGES)
        current_player = self.players[self.current_player_index]
        # If the player has an empty hand and is expected to play from hand, skip to next phase.
        if not current_player.hand and self.stage_index in (0, 1):
            self.go_next_stage()
        return

    def go_next_player(self) -> None:
        self.current_player_index = (self.current_player_index + 1) % len(self.players)

    def deal_cards(self) -> None:
        for player in self.players:
            for _ in range(5):
                player.hand.append(self.deck.pop())

    def market_to_dict(self) -> List[Dict]:
        return [card.to_dict() for card in self.market]

    def cash_in(self, field: Field, player: Player) -> None:
        '''Adds coins to player and clears field'''
        value: int = field.get_trade_value()
        player.coins += value
        field.cards = field.cards[value:]
        for card in field.cards:
            self.discards.cards.append(card)
        field.cards = []

    def draw_cards(self, card_count: int) -> List[Card]:
        '''Draws card for user and shuffles if necessary'''
        cards: List[Card] = []
        #TODO There is a bug in here at end game. Fix it.
        for i in range(card_count):
            if self.deck.get_length() == 0:
                if self.playthrough == 2:
                    self.end_game()
                    return None
                self.playthrough += 1
                self.deck.cards = self.discards.take_all()
                self.deck.shuffle()
            cards.append(self.deck.pop())
        return cards

    def end_game(self):
        '''End the game'''
        # Make game completed
        self.status = "Completed"
        for player in self.players:
            for field in player.fields:
                self.cash_in(field, player)

        player_ranks = sorted(self.players, key=getattr('coins'), reverse=True)
        self.winner = player_ranks[0].name

    def verify_field(self, player: Player, field_index: int):
        if field_index not in range(0, len(player.fields)):
            return util.error('Invalid field index')
        if not player.fields[field_index].enabled:
            return util.error('Field not yet bought')
        return {'field': player.fields[field_index]}

    def ids_to_tcs(self, player: Player, card_ids: List[str]) -> List[TradingCard]:
        '''Call with a player and the ids they want to trade'''
        tcs: List[TradingCard] = []
        market_cards = [card for card in self.market if card.id in  card_ids]
        hand_cards = [card for card in player.hand if card.id in card_ids]
        tcs += [TradingCard(card, self.market, 'Market') for card in market_cards]
        player_hand_name: str = "{}'s hand".format(player.name)
        tcs += [TradingCard(card, player.hand, player_hand_name) for card in hand_cards]
        return tcs

    def pop_card_from_list(self, card_id: str, location: List[Card]):
        card = util.shrink([card for card in location if card.id == card_id])
        other_cards = [card for card in location if card.id != card_id]
        location.clear()
        for other_card in other_cards:
            location.append(other_card)
        return card

    def check_if_pending_cards(self, player: Player):
        if player.pending_cards:
            return util.error("Pending cards must be played first")
        return None

    def add_to_market(self, cards: List[Card]):
        '''Adds card to market'''
        self.market += cards
