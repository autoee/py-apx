import apx
import remotefile
import abc

class DataListener(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def on_data(self, port_id, port_name, data):
        """
        called by apx.client when a require port has updated its data
        """

@apx.NodeDataClient.register
class Client:
    """
    APX Client class for a single APX node
    """
    def __init__(self, node=None):
        self.fileManager=apx.FileManager()
        self.socketAdapter=remotefile.TcpSocketAdapter()
        self.attach_node(node)
        self.dataListener=None

    def attach_node(self, node):
        """
        Attaches existing APX node to the client
        """
        self.node=node if isinstance(node, apx.Node) else None
        if self.node is not None:
            self.nodeData=apx.NodeData(node)
            inPortDataFile = self.nodeData.inPortDataFile
            outPortDataFile = self.nodeData.outPortDataFile
            definitionDataFile = self.nodeData.definitionFile
            if inPortDataFile is not None:
                self.fileManager.requestRemoteFile(inPortDataFile)
            if outPortDataFile is not None:
                self.fileManager.attachLocalFile(outPortDataFile)
            if definitionDataFile is not None:
                self.fileManager.attachLocalFile(definitionDataFile)
            self.nodeData.nodeDataClient=self
            self.providePortMap={}
            self.fileManager.start()

    def create_node(self, apxText):
        """
        Creates new APX node from a string
        """
        parser = apx.Parser()
        node = parser.loads(apxText)
        if node is not None:
            self.attach_node(node)

    def connect_tcp(self, address, port):
        self.socketAdapter.setReceiveHandler(self.fileManager)
        if self.socketAdapter.connect(address, port):
            self.socketAdapter.start()
            return True
        else:
            return False
    
    def find(self, name):
        """
        Finds port in attached node
        """
        if self.node is not None:
            return self.node.find(name)
        return None
    
    def stop(self):
        self.socketAdapter.stop()
        self.fileManager.stop()

    def set_listener(self, dataListener):
        self.dataListener=dataListener

    def on_require_port_data(self, port, value):
        if self.dataListener:
            self.dataListener.on_data(port, value)

    def read(self, identifier):
        if self.node is not None and self.nodeData is not None:
            if isinstance(identifier, apx.Port):
                port = identifier
                test_port = self.node.requirePorts[port.id]
                if test_port is not port:
                    if isinstance(port, apx.Provide):
                        raise ValueError('Cannot read from a provide port: {0.name}.{1.name}'.format(self.node, port))
                    else:
                        raise ValueError('Port {0.name} is not a require port of node {1.name}'.format(self.port, self.node))
            if isinstance(identifier, str):
                port = self.node.find(identifier)
                if not isinstance(port, apx.RequirePort):
                    raise ValueError('Port {0.name} is not a require port of node {1.name}'.format(self.port, self.node))
            elif isinstance(identifier, int):
                port = self.node.requirePorts[identifier]
                if port is None:
                    raise ValueError('Port {0.name} is not a require port of node {1.name}'.format(self.port, self.node))
            return self.nodeData.read_require_port(port.id)

    def write(self, identifier, value):
        if self.node is not None and self.nodeData is not None:
            if isinstance(identifier, apx.Port):
                port = identifier
                test_port = self.node.providePorts[port.id]
                if test_port is not port:
                    if isinstance(port, apx.RequirePort):
                        raise ValueError('Cannot write to require port {0.name}.{1.name}'.format(self.node, port))
                    else:
                        raise ValueError('Port {0.name} is not a provide port of node {1.name}'.format(self.port, self.node))
            if isinstance(identifier, str):
                port = self.node.find(identifier)
                if not isinstance(port, apx.ProvidePort):
                    raise ValueError('Port {0.name} is not a provide port of node {1.name}'.format(self.port, self.node))
            elif isinstance(identifier, int):
                port = self.node.providePorts[identifier]
                if port is None:
                    raise ValueError('Port {0.name} is not a provide port of node {1.name}'.format(self.port, self.node))
            self.nodeData.write_provide_port(port.id, value)
