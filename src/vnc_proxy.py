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
    
    def __init__(self, transport, peer_proxy, factory):
        
        super().__init__()
        
        self.transport = transport
        self.peer_proxy = peer_proxy
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
    
    def _handleInitial(self):
        buffer = b''.join(self._packet)
        msg = buffer[:12]
        
        # report version to the root factory
        is_first_trial = self.peer_proxy.pv_server is None
        self.peer_proxy.pv_server = msg
        
        if b'\n' in msg:
            version = 3.3
            if msg[:3] == b'RFB':
                version_server = float(msg[3:-1].replace(b'0', b''))
                SUPPORTED_VERSIONS = (3.3, 3.7, 3.8)
                if version_server == 3.889: # Apple Remote Desktop
                    version_server = 3.8
                if version_server in SUPPORTED_VERSIONS:
                    version = version_server
                else:
                    log.msg("Protocol version %.3f not supported"
                            % version_server)
                    version = max(filter(
                        lambda x: x <= version_server, SUPPORTED_VERSIONS))
            
            if is_first_trial:
                parts = str(version).split('.')
                self.transport.write(
                    bytes(b"RFB %03d.%03d\n" % (int(parts[0]), int(parts[1]))))
            
            # wait server decide pv
            version = self.peer_proxy.decide_pv()
            if version is None:
                return
            
            remained_buffer = buffer[12:]
            self._packet[:] = [remained_buffer]
            self._packet_len = len(remained_buffer)
            self._handler = self._handleExpected
            self._version = version
            self._version_server = version_server
            if version < 3.7:
                self.expect(self._handleAuth, 4)
            else:
                self.expect(self._handleNumberSecurityTypes, 1)
        else:
            self._packet[:] = [buffer]
            self._packet_len = len(buffer)


class CustomVNCLoggingClientProxy(portforward.ProxyClient):

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)
        self.internal_protocol = None

    def connectionMade(self):

        super().connectionMade()
        self.internal_protocol = DummyRFBClient(NullTransport(), self.peer, self.peer.factory)
        self.internal_protocol.connectionMade()

    def connectionLost(self, reason):
        
        print('client proxy', 'connectionLost', reason)
        super().connectionLost(reason)
        if self.internal_protocol:
            self.internal_protocol.connectionLost(reason)

    def dataReceived(self, data):
        
        print('CustomVNCLoggingClientProxy', 'dataReceived', len(data))
        super().dataReceived(data)
        if self.internal_protocol:
            self.internal_protocol.dataReceived(data)


class CustomVNCLoggingClientFactory(portforward.ProxyClientFactory):
    
    protocol = CustomVNCLoggingClientProxy


class DummyRFBServer(rfb.RFBServer):
    
    def __init__(self, transport, proxy, factory):
    
        super().__init__()

        self.transport = transport
        self.proxy = proxy
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
    
    def _handle_version(self):
        
        msg = self.buffer[:12]
        if not msg.startswith(b'RFB 003.') and msg.endswith(b'\n'):
            self.transport.loseConnection()
            return
        
        # report version to the root factory
        self.proxy.pv_client = msg
        # decide version
        version = self.proxy.decide_pv()
        if version is None:
            return
        
        self.buffer = self.buffer[12:]
        
        if version < 3.7:
            if self.factory.password_required:
                self._handler = self._handle_VNCAuthResponse, 16
            else:
                self._handler = self._handle_clientInit, 1
        else:
            # XXX send security v3.7+
            self._handler = self._handle_security, 1
        

class CustomVNCLoggingServerProxy(portforward.ProxyServer):
    
    clientProtocolFactory = CustomVNCLoggingClientFactory
    reconnect_tolerance = 1
    
    def __init__(self, *args, **kwargs):
        print(args, kwargs)
        super().__init__(*args, **kwargs)
        self.internal_protocol = None
        
        self.pv_server = None
        self.pv_client = None
    
    def decide_pv(self):
        
        if self.pv_server is None or self.pv_client is None:
            return None
        
        to_float = lambda x: float('{}.{}'.format(int(x[4:7].decode()), int(x[8:11].decode())))
        return min(to_float(self.pv_server), to_float(self.pv_client))
    
    def connectionMade(self):
        
        t_connection_made = time.time()
        
        super().connectionMade()
        self.internal_protocol = DummyRFBServer(NullTransport(), self, self.factory)
        self.internal_protocol.connectionMade()
        
        host = self.transport.getPeer().host
        last_t_connection_lost = self.factory.time_connection_lost.get(host, None)
        
        restarted = False
        if last_t_connection_lost is not None and \
            t_connection_made - last_t_connection_lost < self.reconnect_tolerance:
            s = self.factory.connection_lost_schedule.get(host, None)
            if (s is not None) and s.active():
                s.cancel()
                del self.factory.connection_lost_schedule[host]
            restarted = True
        self.on_connection_made(restarted)

    def connectionLost(self, reason):
        
        t_connection_lost = time.time()

        super().connectionLost(reason)
        if self.internal_protocol:
            self.internal_protocol.connectionLost(reason)
        
        host = self.transport.getPeer().host
        self.factory.time_connection_lost[host] = t_connection_lost
        self.factory.connection_lost_schedule[host] = \
            reactor.callLater(self.reconnect_tolerance, self.on_connection_lost, reason)
    
    def on_connection_made(self, restarted):
        pass
    
    def on_connection_lost(self, reason):
        pass
    
    def dataReceived(self, data):
        
        print('CustomVNCLoggingServerProxy', 'dataReceived', len(data))
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
        self.time_connection_lost = {}
        self.connection_lost_schedule = {}

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

