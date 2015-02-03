from tornado.ioloop import IOLoop
from tornado.web import RequestHandler, Application, url
import tornado.gen
import tornadis
import logging

logging.basicConfig(level=logging.WARNING)
POOL = tornadis.ClientPool(max_size=15)


class HelloHandler(RequestHandler):

    @tornado.gen.coroutine
    def get(self):
        pong = "PONG"
        with (yield POOL.connected_client()) as client:
            reply = yield client.call("PING")
            reply = yield client.call("PING")
            reply = yield client.call("PING")
        self.write("Hello, %s" % pong)
        self.finish()


def make_app():
    return Application([
        url(r"/", HelloHandler),
        ])


def main():
    app = make_app()
    app.listen(8888)
    IOLoop.current().start()

main()
