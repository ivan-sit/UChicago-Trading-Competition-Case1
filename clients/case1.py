#!/usr/bin/env python

from collections import defaultdict
from typing import DefaultDict, Dict, Tuple
from utc_bot import UTCBot, start_bot
import math
import proto.utc_bot as pb
import betterproto
import asyncio
import re

#place orderbook
#
#update penny best ask and bid by 

#is the the given data only for ordering

# how to limit risk --> does that just mean the spread have to be within 1000

START_BID = 100
START_ASK = 700

START_FAIR = 330

DAYS_IN_MONTH = 21
DAYS_IN_YEAR = 252
INTEREST_RATE = 0.02
NUM_FUTURES = 14
TICK_SIZE = 0.01
FUTURE_CODES = [chr(ord('A') + i) for i in range(NUM_FUTURES)] # Suffix of monthly future code
CONTRACTS = ['SBL'] +  ['LBS' + c for c in FUTURE_CODES] + ['LLL']
CARRYING_COST = 0.2
ETF_CODE = "LLL"

ORDER_SIZE = 100

ORDER_L1 = 15 # 25
ORDER_L2 = 10 # 10
ORDER_L3 = 5 # 5

L1_SPREAD = 0.02
L2_SPREAD = L1_SPREAD*2
L3_SPREAD = L1_SPREAD*3
L4_SPREAD = L1_SPREAD*4

class OpenOrders:
    def __init__(self, contract):
        self.contract_name = contract
        self.num_open_orders = 0
        self.price_to_id = {} # price to id dict

        self.id_to_price = {} # id to price dict

        self.id_to_qty = {} # id to qty dict

    # adjusting the quantity based on the id - remove order from OpenOrders if quantity is now 0.
    def adjust_qty(self, id, adj):
        self.id_to_qty[id] += adj

        # deleting order
        if self.id_to_qty[id] == 0:
            self.num_open_orders -= 1
            price = self.id_to_price[id]

            try:
                del self.id_to_price[id]
                del self.price_to_id[price]
                del self.id_to_qty[id]
            except Exception as e:
                print("Error (0) deleting filled order: ",e)


    # adding the order to the price_to_id dict if we don't already have any id in this price
    # NOT USED
    def add_order(self, price, id, qty):
        if not price in self.price_to_id:
            self.price_to_id[price] = id
            self.num_open_orders += 1
        if not id in self.id_to_qty:
            self.id_to_qty[id] = qty
        if not id in self.id_to_price:
            self.id_to_price[id] = price

    def modify_order(self,price,qty,old_id,new_id):
        # create order (if there is no order with matching ID)
        if (old_id == new_id):
            if not old_id in self.id_to_price:
                self.id_to_price[old_id] = price
                self.price_to_id[price] = old_id
                self.id_to_qty[old_id] = qty
                self.num_open_orders += 1
            # update order
            else:
                # delete old price to data
                try:
                    del self.price_to_id[self.id_to_price[old_id]]
                except Exception as e:
                    print("Error (1) deleting filled order: ",e)

                # add new price to id
                self.price_to_id[price] = old_id
                self.id_to_price[old_id] = price
                self.id_to_qty[old_id] = qty
        else:
            if not old_id in self.id_to_price:
                self.id_to_price[new_id] = price
                self.price_to_id[price] = new_id
                self.id_to_qty[new_id] = qty
                self.num_open_orders += 1
            else:
                # old order still exists so delete and then update with new values

                # delete old price, id, and qty
                try:
                    del self.price_to_id[self.id_to_price[old_id]] # error is no price in price_to_id for old price
                    del self.id_to_price[old_id]
                    del self.id_to_qty[old_id]
                except Exception as e:
                    print("Error (2) deleting filled order: ",e)

                # add new price to new id
                self.price_to_id[price] = new_id
                self.id_to_price[new_id] = price
                self.id_to_qty[new_id] = qty


    # getting the quantity based on the price
    def get_qty(self, price):
        p_id = self.price_to_id[price]
        return self.id_to_qty[p_id]

    def get_id(self, price):
        return self.price_to_id[price]

class Case1Bot(UTCBot):
    """
    An example bot
    """
    etf_suffix = ''
    async def create_etf(self, qty: int):
        '''
        Creates qty amount the ETF basket
        DO NOT CHANGE
        '''
        if len(self.etf_suffix) == 0:
            return pb.SwapResponse(False, "Unsure of swap")
        return await self.swap("create_etf_" + self.etf_suffix, qty)

    async def redeem_etf(self, qty: int):
        '''
        Redeems qty amount the ETF basket
        DO NOT CHANGE
        '''
        if len(self.etf_suffix) == 0:
            return pb.SwapResponse(False, "Unsure of swap")
        return await self.swap("redeem_etf_" + self.etf_suffix, qty) 
    
    async def days_to_expiry(self, asset):
        '''
        Calculates days to expiry for the future
        '''
        future = ord(asset[-1]) - ord('A')
        expiry = 21 * (future + 1)
        return self._day - expiry

    async def handle_exchange_update(self, update: pb.FeedMessage):
        '''
        Handles exchange updates
        '''
        kind, _ = betterproto.which_one_of(update, "msg")
        #Competition event messages
        if kind == "generic_msg":
            msg = update.generic_msg.message
            # print(msg)
            # Used for API DO NOT TOUCH
            if 'trade_etf' in msg:
                self.etf_suffix = msg.split(' ')[1]
                
            # Updates current weather
            if "Weather" in update.generic_msg.message:
                msg = update.generic_msg.message
                weather = float(re.findall("\d+\.\d+", msg)[0])
                self._weather_log.append(weather)
                
            # Updates date
            if "Day" in update.generic_msg.message:
                self._day = int(re.findall("\d+", msg)[0])
                            
            # Updates positions if unknown message (probably etf swap)
            else:
                resp = await self.get_positions()
                if resp.ok:
                    self.positions = resp.positions
                    
        elif kind == "market_snapshot_msg":
            # print("received market snapshot message")
            for contract in CONTRACTS:
                book = update.market_snapshot_msg.books[contract]
                # print(update.market_snapshot_msg)
                self._best_bid[contract] = float(book.bids[0].px)
                self._best_ask[contract] = float(book.bids[0].px)

                # remove our orders from boo TODO
                for price in self.open_orders[contract].price_to_id.keys():
                    quantity = self.open_orders[contract].get_qty(price)

                    #print("open order price: ", price, contract, quantity, self.open_orders[contract].price_to_id[price])

                    if (quantity > 0): # long
                        #print("book bid: ",end="")
                        for i in range (len(book.bids)):
                            #print(book.bids[i].px, " ",end="")
                            if (round(float(book.bids[i].px), 2) < price):
                                break
                            if (round(float(book.bids[i].px), 2) == price):
                                book.bids[i].qty -= quantity
                                if (book.bids[i].qty == 0):
                                    book.bids.pop(i)
                                #print("BOOK changed")
                                break
                    else: # short
                        #print("book ask: ",end="")
                        for i in range (len(book.asks)):
                            #print(book.asks[i].px," ",end="")
                            if (round(float(book.asks[i].px), 2) > price):
                                break
                            if (round(float(book.asks[i].px), 2) == price):
                                book.asks[i].qty += quantity
                                if (book.asks[i].qty == 0):
                                    book.asks.pop(i)
                                #print("BOOK changed")
                                break


                if len(book.bids) != 0:
                    best_bid = book.bids[0]
                    self.__orders[contract]['Best Bid']['Price'] = float(best_bid.px)
                    self.__orders[contract]['Best Bid']['Quantity'] = best_bid.qty

                if len(book.asks) != 0:
                    best_ask = book.asks[0]
                    self.__orders[contract]['Best Ask']['Price'] = float(best_ask.px)
                    self.__orders[contract]['Best Ask']['Quantity'] = best_ask.qty
            


    async def handle_round_started(self):

        start_fair = START_FAIR
        ### Current day
        self._day = 0
        ### Best Bid in the order book
        self._best_bid: Dict[str, float] = defaultdict(
            lambda: 0
        )
        ### Best Ask in the order book
        self._best_ask: Dict[str, float] = defaultdict(
            lambda: 0
        )
        ### Order book for market making
        self.__orders: DefaultDict[str, DefaultDict[str, float]] = defaultdict(
            lambda: ("", 0)
        )
        ### TODO Recording fair price for each asset
        self._fair_price: DefaultDict[str, float] = defaultdict(
            lambda: start_fair
        )
        ### TODO spread fair price for each asset
        self._spread: DefaultDict[str, float] = defaultdict(
            lambda: L1_SPREAD
        )

        ### TODO order size for market making positions
        self._quantity: DefaultDict[str, int] = defaultdict(
            lambda: 1
        )
        

        self.open_orders = {}
        self.order_ids = {}
        ### List of weather reports
        self._weather_log = []



        for month in CONTRACTS:
            # TODO make other (for different levels of orders)
            self.order_ids[month+' bid'] = ''
            self.order_ids[month+' ask'] = ''

            self.order_ids[month+' l1 bid'] = ''
            self.order_ids[month+' l1 ask'] = ''

            self.order_ids[month+' l2 bid'] = ''
            self.order_ids[month+' l2 ask'] = ''

            self.order_ids[month+' l3 bid'] = ''
            self.order_ids[month+' l3 ask'] = ''

            self.order_ids[month+' l4 bid'] = ''
            self.order_ids[month+' l4 ask'] = ''


            self._fair_price[month] = start_fair

            self.__orders[month] = {
                'Best Bid':{'Price':0,'Quantity':0},
                'Best Ask':{'Price':0,'Quantity':0}
                }

            self._quantity[month] = 0

            self.open_orders[month] = OpenOrders(month)
        
        await asyncio.sleep(.1)
        # asyncio.create_task(self.example_redeem_etf())
        asyncio.create_task(self.update_quotes())

        ###
        ### TODO START ASYNC FUNCTIONS HERE




    # This is an example of creating and redeeming etfs
    # You can remove this in your actual bots.
    async def example_redeem_etf(self):
        while True:
            redeem_resp = await self.redeem_etf(1) #just figure out how to redeem and call no need to worry about the functions itself
            create_resp = await self.create_etf(5)
            await asyncio.sleep(1)

    async def update_quotes(self):
        '''
        This function updates the quotes at each time step. In this sample implementation we
        are always quoting symetrically about our predicted fair prices, without consideration
        for our current positions. We don't reccomend that you do this for the actual competition.
        TODO: determine strat + read blog for what was used
        '''
        while True:
            # if we have seen a rain report then trade (change later)
            #if ( self.rain ):

            # update fairs UNUSED
            await self.calculate_fair_price()

            for contract in CONTRACTS:
                penny_ask_price = self.__orders[contract]["Best Ask"]["Price"] - .01
                penny_bid_price = self.__orders[contract]["Best Bid"]["Price"] + .01

                if (self.__orders[contract]["Best Ask"]["Price"] == 0 or self.__orders[contract]["Best Bid"]["Price"] == 0):
                    penny_ask_price = START_ASK
                    penny_bid_price = START_BID
                    print(penny_ask_price, penny_bid_price)

                if ( penny_ask_price - penny_bid_price ) > 0 :

                    old_bid_id = self.order_ids[contract+' bid']
                    old_ask_id = self.order_ids[contract+' ask']
                    # penny bid/ask
                    bid_response = await self.modify_order(
                        self.order_ids[contract+' bid'],
                        contract,
                        pb.OrderSpecType.LIMIT,
                        pb.OrderSpecSide.BID,
                        ORDER_SIZE,
                        round(penny_bid_price, 2))

                    ask_response = await self.modify_order(
                        self.order_ids[contract+' ask'],
                        contract,
                        pb.OrderSpecType.LIMIT,
                        pb.OrderSpecSide.ASK,
                        ORDER_SIZE,
                        round(penny_ask_price, 2))

                    assert bid_response.ok
                    self.order_ids[contract+' bid'] = bid_response.order_id

                    self.open_orders[contract].modify_order(round(penny_bid_price, 2),ORDER_SIZE,old_bid_id, bid_response.order_id )


                    assert ask_response.ok
                    self.order_ids[contract+' ask'] = ask_response.order_id
                    self.open_orders[contract].modify_order(round(penny_ask_price, 2), -ORDER_SIZE, old_ask_id, ask_response.order_id )

                    # levels 1
                    if (penny_bid_price - L1_SPREAD) > 0:
                        old_bid_id = self.order_ids[contract+' l1 bid']
                        old_ask_id = self.order_ids[contract+' l1 ask']

                        bid_response = await self.modify_order(
                            self.order_ids[contract+' l1 bid'],
                            contract,
                            pb.OrderSpecType.LIMIT,
                            pb.OrderSpecSide.BID,
                            ORDER_L1,
                            round(penny_bid_price - L1_SPREAD, 2))

                        ask_response = await self.modify_order(
                            self.order_ids[contract+' l1 ask'],
                            contract,
                            pb.OrderSpecType.LIMIT,
                            pb.OrderSpecSide.ASK,
                            ORDER_L1,
                            round(penny_ask_price + L1_SPREAD, 2))

                        #assert bid_response.ok
                        self.order_ids[contract+' l1 bid'] = bid_response.order_id
                        self.open_orders[contract].modify_order(round(penny_bid_price - L1_SPREAD, 2),ORDER_L1, old_bid_id,bid_response.order_id )


                        #assert ask_response.ok
                        self.order_ids[contract+' l1 ask'] = ask_response.order_id
                        self.open_orders[contract].modify_order(round(penny_ask_price + L1_SPREAD, 2),-ORDER_L1, old_ask_id,ask_response.order_id )

                    # levels 2
                    if (penny_bid_price - L2_SPREAD) > 0:
                        old_bid_id = self.order_ids[contract+' l2 bid']
                        old_ask_id = self.order_ids[contract+' l2 ask']

                        bid_response = await self.modify_order(
                            self.order_ids[contract+' l2 bid'],
                            contract,
                            pb.OrderSpecType.LIMIT,
                            pb.OrderSpecSide.BID,
                            ORDER_L2,
                            round(penny_bid_price - L2_SPREAD, 2))

                        ask_response = await self.modify_order(
                            self.order_ids[contract+' l2 ask'],
                            contract,
                            pb.OrderSpecType.LIMIT,
                            pb.OrderSpecSide.ASK,
                            ORDER_L2,
                            round(penny_ask_price + L2_SPREAD, 2))

                        #assert bid_response.ok
                        self.order_ids[contract+' l2 bid'] = bid_response.order_id
                        self.open_orders[contract].modify_order(round(penny_bid_price - L2_SPREAD, 2),ORDER_L2, old_bid_id,bid_response.order_id )


                        #assert ask_response.ok
                        self.order_ids[contract+' l2 ask'] = ask_response.order_id
                        self.open_orders[contract].modify_order(round(penny_ask_price + L2_SPREAD, 2),-ORDER_L2, old_ask_id,ask_response.order_id )


                    # levels 3
                    if (penny_bid_price - L3_SPREAD) > 0:
                        old_bid_id = self.order_ids[contract+' l3 bid']
                        old_ask_id = self.order_ids[contract+' l3 ask']

                        bid_response = await self.modify_order(
                            self.order_ids[contract+' l3 bid'],
                            contract,
                            pb.OrderSpecType.LIMIT,
                            pb.OrderSpecSide.BID,
                            ORDER_L3,
                            round(penny_bid_price - L3_SPREAD, 2))

                        ask_response = await self.modify_order(
                            self.order_ids[contract+' l3 ask'],
                            contract,
                            pb.OrderSpecType.LIMIT,
                            pb.OrderSpecSide.ASK,
                            ORDER_L3,
                            round(penny_ask_price + L3_SPREAD, 2))

                        #assert bid_response.ok
                        self.order_ids[contract+' l3 bid'] = bid_response.order_id
                        self.open_orders[contract].modify_order(round(penny_bid_price - L3_SPREAD, 2),ORDER_L3, old_bid_id,bid_response.order_id )


                        #assert ask_response.ok
                        self.order_ids[contract+' l3 ask'] = ask_response.order_id
                        self.open_orders[contract].modify_order(round(penny_ask_price + L3_SPREAD, 2),-ORDER_L3, old_ask_id,ask_response.order_id )


            await asyncio.sleep(1)


        
        ###        
        # Starts market making for each asset
        # for asset in CONTRACTS:
            # asyncio.create_task(self.make_market_asset(asset))

   


    ### Helpful ideas
    async def calculate_risk_exposure(self):
        pass
    
    async def calculate_fair_price(self):
         for month in CONTRACTS:

            fair = (self.__orders[month]["Best Bid"]["Price"] + self.__orders[month]["Best Ask"]["Price"]) / 2.0

            self._fair_price[month] = fair if fair > 0 else START_FAIR
        
    async def make_market_asset(self, asset: str):
        while self._day <= DAYS_IN_YEAR:
            ## Old prices
            ub_oid, ub_price = self.__orders["underlying_bid_{}".format(asset)]
            ua_oid, ua_price = self.__orders["underlying_ask_{}".format(asset)]
            
            bid_px = self._fair_price[asset] - self._spread[asset]
            ask_px = self._fair_price[asset] + self._spread[asset]
            
            # If the underlying price moved first, adjust the ask first to avoid self-trades
            if (bid_px + ask_px) > (ua_price + ub_price):
                order = ["ask", "bid"]
            else:
                order = ["bid", "ask"]

            for d in order:
                if d == "bid":
                    order_id = ub_oid
                    order_side = pb.OrderSpecSide.BID
                    order_px = bid_px
                else:
                    order_id = ua_oid
                    order_side = pb.OrderSpecSide.ASK
                    order_px = ask_px

                r = await self.modify_order(
                        order_id = order_id,
                        asset_code = asset,
                        order_type = pb.OrderSpecType.LIMIT,
                        order_side = order_side,
                        qty = self._quantity[asset],
                        px = round_nearest(order_px, TICK_SIZE), 
                    )

                self.__orders[f"underlying_{d}_{asset}"] = (r.order_id, order_px)

        

def round_nearest(x, a):
    return round(round(x / a) * a, -int(math.floor(math.log10(a))))             



if __name__ == "__main__":
    start_bot(Case1Bot)



# !/usr/bin/env python

# from collections import defaultdict
# from typing import DefaultDict, Dict, Tuple
# from utc_bot import UTCBot, start_bot
# import math
# import proto.utc_bot as pb
# import betterproto
# import asyncio
# import re

# DAYS_IN_MONTH = 21
# DAYS_IN_YEAR = 252
# INTEREST_RATE = 0.02
# NUM_FUTURES = 14
# TICK_SIZE = 0.01
# FUTURE_CODES = [chr(ord('A') + i) for i in range(NUM_FUTURES)] # Suffix of monthly future code
# CONTRACTS = ['SBL'] +  ['LBS' + c for c in FUTURE_CODES] + ['LLL']

# class Case1Bot(UTCBot):
#     """
#     An example bot
#     """
#     etf_suffix = ''
#     async def create_etf(self, qty: int):
#         '''
#         Creates qty amount the ETF basket
#         DO NOT CHANGE
#         '''
#         if len(self.etf_suffix) == 0:
#             return pb.SwapResponse(False, "Unsure of swap")
#         return await self.swap("create_etf_" + self.etf_suffix, qty)

#     async def redeem_etf(self, qty: int):
#         '''
#         Redeems qty amount the ETF basket
#         DO NOT CHANGE
#         '''
#         if len(self.etf_suffix) == 0:
#             return pb.SwapResponse(False, "Unsure of swap")
#         return await self.swap("redeem_etf_" + self.etf_suffix, qty) 
    
#     async def days_to_expiry(self, asset):
#         '''
#         Calculates days to expiry for the future
#         '''
#         future = ord(asset[-1]) - ord('A')
#         expiry = 21 * (future + 1)
#         return self._day - expiry

#     async def handle_exchange_update(self, update: pb.FeedMessage):
#         '''
#         Handles exchange updates
#         '''
#         kind, _ = betterproto.which_one_of(update, "msg")
#         #Competition event messages
#         if kind == "generic_msg":
#             msg = update.generic_msg.message
            
#             # Used for API DO NOT TOUCH
#             if 'trade_etf' in msg:
#                 self.etf_suffix = msg.split(' ')[1]
                
#             # Updates current weather
#             if "Weather" in update.generic_msg.message:
#                 msg = update.generic_msg.message
#                 weather = float(re.findall("\d+\.\d+", msg)[0])
#                 self._weather_log.append(weather)
                
#             # Updates date
#             if "Day" in update.generic_msg.message:
#                 self._day = int(re.findall("\d+", msg)[0])
                            
#             # Updates positions if unknown message (probably etf swap)
#             else:
#                 resp = await self.get_positions()
#                 if resp.ok:
#                     self.positions = resp.positions
                    
#         elif kind == "MarketSnapshotMessage":
#             for asset in CONTRACTS:
#                 book = update.market_snapshot_msg.books[asset]
#                 self._best_bid[asset] = float(book.bids[0].px)
#                 self._best_ask[asset] = float(book.bids[0].px)

#         elif kind == "PnLMessage":
#             self._daily_pnl.append(update.pnl_message.pnl)
            


#     async def handle_round_started(self):
#         ### Current day
#         self._day = 0
#         ### Best Bid in the order book
#         self._best_bid: Dict[str, float] = defaultdict(
#             lambda: 0
#         )
#         ### Best Ask in the order book
#         self._best_ask: Dict[str, float] = defaultdict(
#             lambda: 0
#         )

#         ### TODO fair price for each asset
#         self._fair_price: DefaultDict[str, float] = defaultdict(
#             lambda: 0
#         )

#         ### TODO spread fair price for each asset
#         self._spread: DefaultDict[str, float] = defaultdict(
#             lambda: 0
#         )

#         ### TODO order size for market making positions
#         self._quantity: DefaultDict[str, int] = defaultdict(
#             lambda: 0
#         )

#         ### List of weather reports
#         self._weather_log = []

#         ### List of daily PnL values
#         self._daily_pnl = []

#         await asyncio.sleep(.1)
#         ###
#         ### TODO START ASYNC FUNCTIONS HERE
#         ###
#         asyncio.create_task(self.example_redeem_etf())

#         for asset in CONTRACTS:
#             asyncio.create_task(self.make_market_asset(asset))
#             asyncio.create_task(self.calculate_fair_price(asset))

#         asyncio.create_task(self.manage_risk())
#         # asyncio.create_task(self.rebalance_etf())
        
#         # Starts market making for each asset
#         # for asset in CONTRACTS:
#             # asyncio.create_task(self.make_market_asset(asset))

#     # This is an example of creating and redeeming etfs
#     # You can remove this in your actual bots.

#     # async def rebalance_etf(self):
#     #     while self._day <= DAYS_IN_YEAR:
#     #         if self._day % DAYS_IN_MONTH == 0:  # Check if it's the end of the month
#     #             # Perform the rebalancing logic here
#     #             pass
#     #         await asyncio.sleep(1)

#     async def example_redeem_etf(self):
#         while True:
#             redeem_resp = await self.redeem_etf(1)
#             create_resp = await self.create_etf(5)
#             await asyncio.sleep(1)


#     async def calculate_daily_pnl(self):
#         daily_pnl = sum(self._daily_pnl) / len(self._daily_pnl)
#         return daily_pnl

#     async def calculate_sharpe_ratio(self):
#         daily_pnl = await self.calculate_daily_pnl()
#         daily_std_dev = math.sqrt(sum([(x - daily_pnl) ** 2 for x in self._daily_pnl]) / len(self._daily_pnl))
#         sharpe_ratio = (daily_pnl - INTEREST_RATE) / daily_std_dev
#         return sharpe_ratio

#     async def manage_risk(self):
#         while True:
#             sharpe_ratio = await self.calculate_sharpe_ratio()
#             if sharpe_ratio < 1:  # Modify this threshold as needed
#                 # Execute risk management logic, such as reducing position sizes or hedging
#                 pass
#             await asyncio.sleep(1)

#     ### Helpful ideas
#     async def calculate_risk_exposure(self):
#         exposure = 0
#         for asset in CONTRACTS:
#             position = self.positions[asset]
#             fair_price = self._fair_price[asset]
#             exposure += position * fair_price
#         return exposure

#     async def calculate_fair_price(self, asset):
#         if asset == 'SBL':
#             return self._best_ask[asset] * 0.5 + self._best_bid[asset] * 0.5
#         else:
#             days_to_expiry = await self.days_to_expiry(asset)
#             weather = sum(self._weather_log) / len(self._weather_log)
#             fair_price = weather * days_to_expiry / DAYS_IN_YEAR
#             return fair_price

#     async def make_market_asset(self, asset: str):
#         while self._day <= DAYS_IN_YEAR:
#             ## Old prices
#             ub_oid, ub_price = self.__orders["underlying_bid_{}".format(asset)]
#             ua_oid, ua_price = self.__orders["underlying_ask_{}".format(asset)]
            
#             fair_price = await self.calculate_fair_price(asset)
#             self._fair_price[asset] = fair_price
#             spread = 0.01 * fair_price  # You can modify the spread calculations
#             self._spread[asset] = spread
            
#             bid_px = fair_price - spread
#             ask_px = fair_price + spread
            
#             # If the underlying price moved first, adjust the ask first to avoid self-trades
#             if (bid_px + ask_px) > (ua_price + ub_price):
#                 order = ["ask", "bid"]
#             else:
#                 order = ["bid", "ask"]

#             for d in order:
#                 if d == "bid":
#                     order_id = ub_oid
#                     order_side = pb.OrderSpecSide.BID
#                     order_px = bid_px
#                 else:
#                     order_id = ua_oid
#                     order_side = pb.OrderSpecSide.ASK
#                     order_px = ask_px

#                 r = await self.modify_order(
#                         order_id = order_id,
#                         asset_code = asset,
#                         order_type = pb.OrderSpecType.LIMIT,
#                         order_side = order_side,
#                         qty = self._quantity[asset],
#                         px = round_nearest(order_px, TICK_SIZE), 
#                     )

#                 self.__orders[f"underlying_{d}_{asset}"] = (r.order_id, order_px)
                
        

# def round_nearest(x, a):
#     return round(round(x / a) * a, -int(math.floor(math.log10(a))))             



# if __name__ == "__main__":
#     start_bot(Case1Bot)

#!/usr/bin/env python

# from collections import defaultdict
# from typing import DefaultDict, Dict, Tuple
# from utc_bot import UTCBot, start_bot
# import math
# import proto.utc_bot as pb
# import betterproto
# import asyncio
# import re

# DAYS_IN_MONTH = 21
# DAYS_IN_YEAR = 252
# INTEREST_RATE = 0.02
# NUM_FUTURES = 14
# TICK_SIZE = 0.00001
# FUTURE_CODES = [chr(ord('A') + i) for i in range(NUM_FUTURES)] # Suffix of monthly future code
# CONTRACTS = ['SBL'] +  ['LBS' + c for c in FUTURE_CODES] + ['LLL']

# class Case1Bot(UTCBot):
#     """
#     An example bot
#     """
#     etf_suffix = ''
#     async def create_etf(self, qty: int):
#         '''
#         Creates qty amount the ETF basket
#         DO NOT CHANGE
#         '''
#         if len(self.etf_suffix) == 0:
#             return pb.SwapResponse(False, "Unsure of swap")
#         return await self.swap("create_etf_" + self.etf_suffix, qty)

#     async def redeem_etf(self, qty: int):
#         '''
#         Redeems qty amount the ETF basket
#         DO NOT CHANGE
#         '''
#         if len(self.etf_suffix) == 0:
#             return pb.SwapResponse(False, "Unsure of swap")
#         return await self.swap("redeem_etf_" + self.etf_suffix, qty) 
    
#     async def days_to_expiry(self, asset):
#         '''
#         Calculates days to expiry for the future
#         '''
#         future = ord(asset[-1]) - ord('A')
#         expiry = 21 * (future + 1)
#         return self._day - expiry

#     async def handle_exchange_update(self, update: pb.FeedMessage):
#         '''
#         Handles exchange updates
#         '''
#         kind, _ = betterproto.which_one_of(update, "msg")
#         #Competition event messages
#         if kind == "generic_msg":
#             msg = update.generic_msg.message
            
#             # Used for API DO NOT TOUCH
#             if 'trade_etf' in msg:
#                 self.etf_suffix = msg.split(' ')[1]
                
#             # Updates current weather
#             if "Weather" in update.generic_msg.message:
#                 msg = update.generic_msg.message
#                 weather = float(re.findall("\d+\.\d+", msg)[0])
#                 self._weather_log.append(weather)
                
#             # Updates date
#             if "Day" in update.generic_msg.message:
#                 self._day = int(re.findall("\d+", msg)[0])
                            
#             # Updates positions if unknown message (probably etf swap)
#             else:
#                 resp = await self.get_positions()
#                 if resp.ok:
#                     self.positions = resp.positions
                    
#         elif kind == "MarketSnapshotMessage":
#             for asset in CONTRACTS:
#                 book = update.market_snapshot_msg.books[asset]
#                 self._best_bid[asset] = float(book.bids[0].px)
#                 self._best_ask[asset] = float(book.bids[0].px)
            


#     async def handle_round_started(self):
#         ### Current day
#         self._day = 0
#         ### Best Bid in the order book
#         self._best_bid: Dict[str, float] = defaultdict(
#             lambda: 0
#         )
#         ### Best Ask in the order book
#         self._best_ask: Dict[str, float] = defaultdict(
#             lambda: 0
#         )
#         ### Order book for market making
#         self.__orders: DefaultDict[str, Tuple[str, float]] = defaultdict(
#             lambda: ("", 0)
#         )
#         ### TODO Recording fair price for each asset
#         self._fair_price: DefaultDict[str, float] = defaultdict(
#             lambda: 3
#         )
#         ### TODO spread fair price for each asset
#         self._spread: DefaultDict[str, float] = defaultdict(
#             lambda: 3
#         )

#         ### TODO order size for market making positions
#         self._quantity: DefaultDict[str, int] = defaultdict(
#             lambda: 1
#         )
        
#         ### List of weather reports
#         self._weather_log = []
        
#         await asyncio.sleep(.1)
#         ###
#         ### TODO START ASYNC FUNCTIONS HERE
#         ###
#         asyncio.create_task(self.example_redeem_etf())
        
#         # Starts market making for each asset
#         for asset in CONTRACTS:
#             asyncio.create_task(self.make_market_asset(asset))

#     # This is an example of creating and redeeming etfs
#     # You can remove this in your actual bots.
#     async def example_redeem_etf(self):
#         while True:
#             redeem_resp = await self.redeem_etf(1)
#             create_resp = await self.create_etf(5)
#             await asyncio.sleep(1)


#     ### Helpful ideas
#     async def calculate_risk_exposure(self):
#         pass
    
#     async def calculate_fair_price(self, asset):
#         pass
        
#     async def make_market_asset(self, asset: str):
#         while self._day <= DAYS_IN_YEAR:
#             ## Old prices
#             ub_oid, ub_price = self.__orders["underlying_bid_{}".format(asset)]
#             ua_oid, ua_price = self.__orders["underlying_ask_{}".format(asset)]
            
#             bid_px = self._fair_price[asset] - self._spread[asset]
#             ask_px = self._fair_price[asset] + self._spread[asset]
            
#             # If the underlying price moved first, adjust the ask first to avoid self-trades
#             if (bid_px + ask_px) > (ua_price + ub_price):
#                 order = ["ask", "bid"]
#             else:
#                 order = ["bid", "ask"]

#             for d in order:
#                 if d == "bid":
#                     order_id = ub_oid
#                     order_side = pb.OrderSpecSide.BID
#                     order_px = bid_px
#                 else:
#                     order_id = ua_oid
#                     order_side = pb.OrderSpecSide.ASK
#                     order_px = ask_px

#                 r = await self.modify_order(
#                         order_id = order_id,
#                         asset_code = asset,
#                         order_type = pb.OrderSpecType.LIMIT,
#                         order_side = order_side,
#                         qty = self._quantity[asset],
#                         px = round_nearest(order_px, TICK_SIZE), 
#                     )

#                 self.__orders[f"underlying_{d}_{asset}"] = (r.order_id, order_px)
                
        

# def round_nearest(x, a):
#     return round(round(x / a) * a, -int(math.floor(math.log10(a))))             



# if __name__ == "__main__":
#     start_bot(Case1Bot)
