import time
import signal 
import requests
from time import sleep

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

#max orders per second
ORDER_LIMIT = 5

#max size per order
MAX_SIZE = 1000

#target total volume
TOTAL_VOLUME = 20000

#order counter
COUNT = int(TOTAL_VOLUME/MAX_SIZE)

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
    sleep(total_speedbumps/number_of_orders)

def main():
    global number_of_orders
    with requests.Session() as s:
        s.headers.update(API_KEY)

        #num of submitted orders < total volume
        while number_of_orders < COUNT:

            start = time.time()
            #buy 1000 shares
            resp = s.post('http://localhost:9999/v1/orders', params = {'ticker': 'BEAV', 
            'type': 'LIMIT', 'quantity': MAX_SIZE, 'price': 20, 'action': 'BUY'})

            #successful
            if(resp.ok):
                transaction_time = time.time() - start
                speedbump(transaction_time)

            #went over trading limit
            else:
                print(resp.json())

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    main()
