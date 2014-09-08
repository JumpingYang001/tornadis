#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# This file is part of tornadis library released under the MIT license.
# See the LICENSE file for more information.

import tornado.ioloop
import tornado.gen
import hiredis
import toro
import io

from tornadis.connection import Connection
from tornadis.pipeline import Pipeline
from tornadis.utils import format_args_in_redis_protocol

# FIXME: error handling


class Client(object):

    def __init__(self, host='localhost', port=6379, ioloop=None):
        self.host = host
        self.port = port
        self.subscribed = False
        self.__reply_queue = toro.Queue()
        self.__ioloop = ioloop or tornado.ioloop.IOLoop.instance()
        self.reader = hiredis.Reader()
        self.__connection = Connection(host=host, port=port,
                                       ioloop=self.__ioloop)

    @tornado.gen.coroutine
    def connect(self):
        yield self.__connection.connect()
        cb1 = self._close_callback
        cb2 = self._read_callback
        self.__connection.register_read_until_close_callback(cb1, cb2)

    def disconnect(self):
        return self._simple_call("QUIT")

    def _disconnect(self):
        self.__connection.disconnect()
        self.__reply_queue = toro.Queue()

    def _close_callback(self, data=None):
        if data is not None:
            self._read_callback(data)
        self._disconnect()

    def _read_callback(self, data=None):
        if data is not None:
            self.reader.feed(data)
            while True:
                reply = self.reader.gets()
                if reply is not False:
                    self.__reply_queue.put_nowait(reply)
                else:
                    break

    def call(self, *args):
        if self.subscribed:
            raise Exception("This client is in subscription mode, "
                            "only pubsub_* command are allowed")
        if len(args) == 1 and isinstance(args[0], Pipeline):
            return self._pipelined_call(args[0])
        else:
            return self._simple_call(*args)

    @tornado.gen.coroutine
    def _simple_call(self, *args):
        msg = format_args_in_redis_protocol(*args)
        yield self.__connection.write(msg)
        reply = yield self.__reply_queue.get()
        raise tornado.gen.Return(reply)

    def _simple_call_without_pop_reply(self, *args):
        msg = format_args_in_redis_protocol(*args)
        return self.__connection.write(msg)

    def pubsub_subscribe(self, *args):
        return self._pubsub_subscribe("SUBSCRIBE", *args)

    def pubsub_psubscribe(self, *args):
        return self._pubsub_subscribe("PSUBSCRIBE", *args)

    @tornado.gen.coroutine
    def _pubsub_subscribe(self, command, *args):
        yield self._simple_call_without_pop_reply(command, *args)
        for _ in args:
            reply = yield self.__reply_queue.get()
            if len(reply) != 3 or reply[0].lower() != command.lower() or \
               reply[2] == 0:
                raise tornado.gen.Return(False)
        self.subscribed = True
        raise tornado.gen.Return(True)

    def pubsub_unsubscribe(self, *args):
        return self._pubsub_unsubscribe("UNSUBSCRIBE", *args)

    def pubsub_punsubscribe(self, *args):
        return self._pubsub_unsubscribe("PUNSUBSCRIBE", *args)

    @tornado.gen.coroutine
    def _pubsub_unsubscribe(self, command, *args):
        yield self._simple_call_without_pop_reply(command, *args)
        reply = None
        for _ in args:
            reply = yield self.__reply_queue.get()
            if reply is None or len(reply) != 3 or \
               reply[0].lower() != command.lower():
                raise tornado.gen.Return(False)
        if reply is not None and reply[2] == 0:
            self.subscribed = False
        raise tornado.gen.Return(True)

    @tornado.gen.coroutine
    def pubsub_pop_message(self, deadline=None):
        if not self.subscribed:
            raise Exception("you must subcribe before using "
                            "pubsub_pop_message")
        try:
            reply = yield self.__reply_queue.get(deadline=deadline)
        except toro.Timeout:
            reply = None
        raise tornado.gen.Return(reply)

    @tornado.gen.coroutine
    def _pipelined_call(self, pipeline):
        buf = io.BytesIO()
        for args in pipeline.pipelined_args:
            msg = format_args_in_redis_protocol(*args)
            buf.write(msg)
        yield self.__connection.write(buf.getvalue())
        buf.close()
        result = []
        while len(result) < pipeline.number_of_stacked_calls:
            reply = yield self.__reply_queue.get()
            result.append(reply)
        raise tornado.gen.Return(result)
