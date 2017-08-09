from card import Card, Deck
import uuid
import json
import asyncio
from util import error, success


class Game:
    STAGES = (
        'First Card',
        'Second Card',
        'Pre Market Flip',
        'Post Market Flip'
    )
    MAX_PLAYERS = 7

    def __init__(self):
        self.players = []
        self.deck = Deck()
        self.playthrough = 0
        self.discards = Deck()
        self.current_player_index = 0
        self.status = 'Awaiting'  # Awaiting, Running, Completed
        self.id = str(uuid.uuid4())[:6]
        self.stage_index = 0
        self.market = {0: None, 1: None}

        self.deck.build_deck()
        self.deck.shuffle()

    def add_player(self, player):
        # First player is host
        if not self.players:
            player.is_host = True
        self.players.append(player)

    def is_full(self):
        if len(self.players) < Game.MAX_PLAYERS:
            return False
        return True

    def start_game(self, player):
        if self.status != 'Awaiting':
            return error('Game has already started')
        if not player.is_host:
            return error('Only host can start game')
        self.deal_cards()
        self.status = 'Running'
        return success('Successfully started game')

    def retrieve_game(self, player):
        return {
            'player_info': player.to_dict_private(),
            'players': [other_player.to_dict_public() for other_player in self.players],
            'deck_count': self.deck.get_length(),
            'playthrough': self.playthrough,
            'discard_count': self.discards.get_length(),
            'current_player': self.players[self.current_player_index].name,
            'status': self.status,
            'game_id': self.id,
            'stage': Game.STAGES[self.stage_index],
            'market': self.market_to_dict()
        }

    def deck_to_market(self, player):
        '''Draws top 2 cards from deck and places them in market'''
        stage_check = self.verify_stage(Game.STAGES[1:3])
        turn_check = self.verify_turn(player)
        if stage_check or turn_check:
            return stage_check or turn_check
        self.add_to_market([self.deck.pop(), self.deck.pop()])
        self.go_next_stage()
        return success('Cards drawn into market')

    def add_to_market(self, cards):
        self.market[0] = cards[0]
        self.market[1] = cards[1]

    def hand_to_field(self, player, field_index):
        '''
        Plays card from users hand to field. No confirmation.
        '''
        result = self.play_card(player, field_index, Game.STAGES[:2])
        return result

    def market_to_field(self, player, field_index, market_index):
        '''
        Plays card from market to field. No confirmation.
        '''
        result = self.play_card(player, field_index, [Game.STAGES[3]], market_index)
        return result

    def play_card(self, player, field_index, valid_stages, market_index=None):
        stage_check = self.verify_stage(valid_stages)
        turn_check = self.verify_turn(player)
        field_check = self.verify_field(player, field_index)
        if stage_check or turn_check or field_check:
            return stage_check or turn_check or field_check

        if market_index is not None:
            card = self.market[market_index]
        else:
            card = player.hand[0]

        field = player.fields[field_index]
        if not field.add_card(card):
            field.cash_in(player, self.discards)
            field.add_card(card)
            if market_index is not None:
                self.market[market_index] = None
            else:
                player.hand = player.hand[1:]
                self.go_next_stage()
            return success('Field cashed in and card successfully played')
        if market_index is not None:
            self.market[market_index] = None
        else:
            player.hand = player.hand[1:]
            self.go_next_stage()
        return success('Card successfully played')

    def deck_to_hand(self, player):
        stage_check = self.verify_stage(Game.STAGES[3])
        turn_check = self.verify_turn(player)
        if stage_check or turn_check:
            return stage_check or turn_check

        for _ in range(2):
            player.hand.append(self.deck.pop())
        self.go_next_stage()
        self.go_next_player()
        return success('Successfully drew two cards for hand')

    def trade_from_market(self, params):
        pass

    def trade_from_hand(self, params):
        pass

    def trade_accept(self, params):
        pass

    def go_next_stage(self):
        self.stage_index = (self.stage_index + 1) % len(Game.STAGES)

    def go_next_player(self):
        self.current_player_index = (self.current_player_index + 1) % len(self.players)

    def verify_stage(self, allowed_stages):
        if Game.STAGES[self.stage_index] not in allowed_stages:
            return error('Invalid move')

    def verify_turn(self, player):
        if player != self.players[self.current_player_index]:
            return error('It is not your turn')

    def verify_field(self, player, field_index):
        if field_index not in range(0, len(player.fields)):
            return error('Invalid field index')
        if not player.fields[field_index].enabled:
            return error('Field not yet bought')

    def deal_cards(self):
        for player in self.players:
            for _ in range(5):
                player.hand.append(self.deck.pop())

    def market_to_dict(self):
        obj = {0: None, 1: None}
        if self.market[0]:
            obj[0] = self.market[0].to_dict()
        if self.market[1]:
            obj[1] = self.market[1].to_dict()
        return obj

    def get_updates(self):
        return
