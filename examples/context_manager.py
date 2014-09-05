import tornado
import tornadis


@tornado.gen.coroutine
def ping_redis(pool, num):
    with (yield pool.connected_client()) as client:
        # client is a connected tornadis.Client instance
        # it will be automatically released to the pool thanks to the
        # "with" keyword
        reply = yield client.call("PING")
        print("reply #%i : %s" % (num, reply))


@tornado.gen.coroutine
def multiple_ping_redis(pool):
    yield [ping_redis(pool, i) for i in range(0, 100)]


def stop_loop(future):
    loop = tornado.ioloop.IOLoop.instance()
    loop.stop()


pool = tornadis.ClientPool(max_size=5)
loop = tornado.ioloop.IOLoop.instance()
future = multiple_ping_redis(pool)
loop.add_future(future, stop_loop)
loop.start()
