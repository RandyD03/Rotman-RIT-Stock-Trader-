import time
import signal 
import requests
from time import sleep
import sys

#exception
class ApiException(Exception):
    pass

#allows CTRL+C
def signal_handler(signum, frame):
    global shutdown
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    shutdown = True

#API key to authenticate with RIT
API_KEY = {'X-API-Key': 'J19CDRHG'}
shutdown = False

#SETTINGS
SPEEDBUMP = 0.2
MAX_VOLUME = 7500
MAX_ORDERS = 50
SPREAD = 0.02
#max orders per second
ORDER_LIMIT = 5

#starting num of orders
number_of_orders = 0

#starting total speed bumps
total_speedbumps = 0

def speedbump(transaction_time):

    global total_speedbumps
    global number_of_orders

    #speed bump of current order
    order_speedbump = -transaction_time +1/ORDER_LIMIT

    #add it to total aggregated value of speed bump
    total_speedbumps += order_speedbump

    number_of_orders += 1

    #sleep for speed bump calculated based on average
    if total_speedbumps/number_of_orders > 0:
        sleep(total_speedbumps/number_of_orders)
    else:
        sleep(SPEEDBUMP)

#returns the current tick of the running case
def get_tick(session):
    resp = session.get('http://localhost:9999/v1/case')
    if resp.ok:
        case = resp.json()
        return case['tick']
    raise ApiException('Authorization error Please check API key.')

#returns the bid and ask first row for a given security
def ticker_bid_ask(session, ticker):
    payload = {'ticker': ticker}
    resp = session.get('http://localhost:9999/v1/securities/book', params = payload)
    if resp.ok:
        book = resp.json()
        return book['bids'][0]['price'], book['asks'][0]['price']
    raise ApiException('Authorization error Please check API key.')

#returns info about all the open sell orders
def open_sells(session):
    resp = session.get('http://localhost:9999/v1/orders?status=OPEN')
    if resp.ok:
        open_sells_volume = 0   #combined volume of all open sells
        ids = []                #all open sell ids
        prices = []             #all open sell prices
        order_volumes = []      #all open sell volumes
        volume_filled = []      #volume filled for each open sell order

        open_orders = resp.json()
        for order in open_orders:
            if order['action'] == 'SELL':
                volume_filled.append(order['quantity_filled'])
                order_volumes.append(order['quantity'])
                open_sells_volume = open_sells_volume + order['quantity']
                prices.append(order['price'])
                ids.append(order['order_id'])
    return volume_filled, open_sells_volume, ids, prices, order_volumes

#returns info about all open buy orders
def open_buys(session):
    resp = session.get('http://localhost:9999/v1/orders?status=OPEN')
    if resp.ok:
        open_buys_volume = 0   #combined volume of all open buys
        ids = []                #all open buy ids
        prices = []             #all open buy prices
        order_volumes = []      #all open buy volumes
        volume_filled = []      #volume filled for each open buy order

        open_orders = resp.json()
        for order in open_orders:
            if order['action'] == 'BUY':
                open_buys_volume += order['quantity']
                volume_filled.append(order['quantity_filled'])
                order_volumes.append(order['quantity'])
                prices.append(order['price'])
                ids.append(order['order_id'])

    return volume_filled, open_buys_volume, ids, prices, order_volumes

# buy and sell the max number of shares
def buy_sell(session, sell_price, buy_price):
    for i in range(MAX_ORDERS):
        session.post('http://localhost:9999/v1/orders', params = {'ticker': 'BEAV',
         'type': 'LIMIT', 'quantity': MAX_VOLUME, 'price': sell_price, 'action': 'SELL'})
        session.post('http://localhost:9999/v1/orders', params = {'ticker': 'BEAV',
         'type': 'LIMIT', 'quantity': MAX_VOLUME, 'price': buy_price, 'action': 'BUY'})

#re-orders all open buys or sells
def re_order(session, number_of_orders, ids, volumes_filled, volumes, price, action):
    for i in range(number_of_orders):
        id = ids[i]
        volume = volumes[i]
        volume_filled = volumes_filled[i]

        #if order is partially filled
        if(volume_filled != 0):
            volume = MAX_VOLUME - volume_filled
        
        #delete then re-purchase
        deleted = session.delete('http://localhost:9999/v1/orders/id'.format(id))
        if(deleted.ok):
            session.post('http://localhost:9999/v1/orders/', params = {'ticker': 'BEAV',
            'type': 'LIMIT', 'quantity': volume, 'price': price, 'action': action})

def main():

    buy_ids = []
    buy_prices = []
    buy_volumes = []
    volume_filled_buys = []
    open_buys_volume = 0

    sell_ids = []
    sell_prices = []
    sell_volumes = []
    volume_filled_sells = []
    open_sells_volume = 0

    #for partial re-orders and one side has been completely filled
    single_side_filled = False
    single_side_transaction_time = 0

    #creates a session to manage connections and requests to the RIT Client
    with requests.Session() as s:
        s.headers.update(API_KEY)
        tick = get_tick(s)

        #while time is between 5 to 295
        while tick > 3 and tick < 296 and not shutdown:
            #update case
            volume_filled_sells, open_sells_volume, sell_ids, sell_prices, sell_volumes = open_sells(s)
            volume_filled_buys, open_buys_volume, buy_ids, buy_prices, buy_volumes = open_buys(s)
            bid_price, ask_price = ticker_bid_ask(s, 'BEAV')

            #check if you have 0 open orders
            if(open_sells_volume == 0 and open_buys_volume == 0):
                #both sides are filled now
                single_side_filled = False

                #calculate spread between bid and ask prices
                bid_ask_spread = ask_price - bid_price

                #set the prices
                sell_price = ask_price
                buy_price = bid_price

                if(bid_ask_spread >= SPREAD):
                    #buy and sell the max number of shares
                    start = time.time()
                    buy_sell(s, sell_price, buy_price)
                    transaction_time = time.time() - start
                    speedbump(transaction_time)

            #there are outstanding open orders
            else:
                #set the prices
                sell_price = ask_price
                buy_price = bid_price
                #one side of the book has no open orders
                if(not single_side_filled and (open_buys_volume == 0 or open_sells_volume == 0)):
                    single_side_filled = True
                    single_side_transaction_time = tick
                
                #ask side has been completely filled
                if(open_sells_volume == 0):
                    #current buy orders are at the top of the book
                    if(buy_price == bid_price):
                        continue

                    elif(tick - single_side_transaction_time >= 3):
                        #calculate potential profits
                        next_buy_price = bid_price + 0.01
                        potential_profit = sell_price - next_buy_price - 0.2

                        #potential profit is >= to a cent or more than 6 seconds
                        if(potential_profit >= 0.01 or tick - single_side_transaction_time >= 6):
                            action = 'BUY'
                            number_of_orders = len(buy_ids)
                            buy_price = bid_price + 0.01
                            price = buy_price
                            ids = buy_ids
                            volumes = buy_volumes
                            volumes_filled = volume_filled_buys

                            #delete buys then re-buy
                            start = time.time()
                            re_order(s, number_of_orders, ids, volumes_filled, volumes, price, action)
                            transaction_time = time.time() - start
                            speedbump(transaction_time)

                #bid side has been completely filled
                elif(open_buys_volume == 0):
                    #current sell orders are at the top of the book
                    if(sell_price == ask_price):
                        continue
                    
                    elif(tick - single_side_transaction_time >= 3):
                        #calculate potential profits
                        next_sell_price = ask_price - 0.01
                        potential_profit = next_sell_price - buy_price - 0.02

                        #potential profit is >= to a cent or more than 6 seconds
                        if(potential_profit >= 0.01 or tick - single_side_transaction_time >=6):
                            action = 'SELL'
                            number_of_orders = len(sell_ids)
                            sell_price = ask_price - 0.01
                            price = sell_price
                            ids = sell_ids
                            volumes = sell_volumes
                            volumes_filled = volume_filled_sells

                            #delete sells then re-sell
                            start = time.time()
                            re_order(s, number_of_orders, ids, volumes_filled, volumes, price, action)
                            transaction_time = time.time() - start
                            speedbump(transaction_time)

            #refresh the case time
            tick = get_tick(s)

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    main()