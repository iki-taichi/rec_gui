# coding: utf-8


from twisted.internet import reactor
from twisted.protocols import portforward
from vncdotool_mini import rfb

import sys
import time
import json
import base64


class NullTransport(object):

    addressFamily = None

    def write(self, data):
        return

    def writeSequence(self, data):
        return

    def setTcpNoDelay(self, enabled):
        return


class DummyRFBClient(rfb.RFBClient):
    
    def __init__(self, transport, factory):
        
        super().__init__()
        
        self.transport = transport
        self.factory = factory    
        self.writer = factory.writer
        
        self.cursor = None
        self.cmask = None
    
    def vncRequestPassword(self):
        
        pass
    
    def vncConnectionMade(self):
        
        pass
    
    def updateCursor(self, x, y, width, height, image, mask):
    
        if self.factory.nocursor:
            return
        
        str_image = base64.b64encode(image).decode('utf-8')
        str_mask = base64.b64encode(mask).decode('utf-8')
        
        if self.writer.running:
            data = {
                'time': time.time(),
                'event': 'cursor',
                'args': [x, y, width, height, str_image, str_mask],
            }
            self.writer(json.dumps(data))
        else:
            data = [x, y, width, height, str_image, str_mask]
            self.writer.set_default('cursor', data)


class CustomVNCLoggingClientProxy(portforward.ProxyClient):

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)
        self.internal_protocol = None

    def connectionMade(self):

        super().connectionMade()
        self.internal_protocol = DummyRFBClient(NullTransport(), self.peer.factory)
        self.internal_protocol.connectionMade()

    def connectionLost(self, reason):
        
        super().connectionLost(reason)
        if self.internal_protocol:
            self.internal_protocol.connectionLost(reason)

    def dataReceived(self, data):

        super().dataReceived(data)
        if self.internal_protocol:
            self.internal_protocol.dataReceived(data)


class CustomVNCLoggingClientFactory(portforward.ProxyClientFactory):
    
    protocol = CustomVNCLoggingClientProxy


class DummyRFBServer(rfb.RFBServer):
    
    def __init__(self, transport, factory):
    
        super().__init__()

        self.transport = transport
        self.factory = factory
        self.writer = factory.writer
        self.buttons = 0
        self.mouse = (None, None)
    
    def handle_keyEvent(self, key, down):

        data = {
            'time': time.time(),
            'event': 'key',
            'args': [key, down]
        }
        self.writer(json.dumps(data))
    
    def handle_pointerEvent(self, x, y, buttonmask):

        data = {
            'time': time.time(),
            'event': 'pointer',
            'args': [x, y, buttonmask]
        }
        self.writer(json.dumps(data))


class CustomVNCLoggingServerProxy(portforward.ProxyServer):
    
    clientProtocolFactory = CustomVNCLoggingClientFactory
    
    def __init__(self, *args, **kwargs):
        
        super().__init__(*args, **kwargs)
        self.internal_protocol = None
    
    def connectionMade(self):
        
        super().connectionMade()
        self.internal_protocol = DummyRFBServer(NullTransport(), self.factory)
        self.internal_protocol.connectionMade()
    
    def connectionLost(self, reason):
        
        super().connectionLost(reason)
        if self.internal_protocol:
            self.internal_protocol.connectionLost(reason)
    
    def dataReceived(self, data):
        
        super().dataReceived(data)
        if self.internal_protocol:
            self.internal_protocol.dataReceived(data)
    
    def _handle_clientInit(self):
        if self.internal_protocol:
            self.internal_protocol._handle_clientInit()


class CustomVNCLoggingServerFactory(portforward.ProxyFactory):

    protocol = CustomVNCLoggingServerProxy

    def __init__(self, 
        *args,
        shared=True,
        pseudocursor=False,
        nocursor=False,
        password_required=False,
        pseudodesktop=False,
        writer=None,
        **kwargs):
        
        super().__init__(*args, **kwargs)
        
        self.shared = shared
        self.pseudocursor = pseudocursor
        self.nocursor = nocursor
        self.password_required = password_required
        self.pseudodesktop = pseudodesktop
        self.writer = writer
        self.listen_port = None

    def listen_tcp(self, listen_port):
        
        self.listen_port = listen_port
        return reactor.listenTCP(listen_port, self)
    

if __name__ == '__main__':
    
    factory = CustomVNCLoggingServerFactory(
        host='localhost', 
        port=5900,
        password_required=True,
        writer=print,
        pseudocursor=True,
    )
    factory.listen_tcp(5902)
    
    reactor.run()
    sys.exit(reactor.exit_status if hasattr(reactor, 'exit_status') else 0)

