import autosar
import apx
import os
from copy import deepcopy
from apx.parser import apx_split_line, Parser




class Node:
    """
    Represents an APX node

    Example:
    >>> import sys
    >>> import apx
    >>> node = apx.Node()
    >>> node.append(apx.ProvidePort('TestSignal1','C'))
    0
    >>> node.append(apx.RequirePort('TestSignal2','S'))
    0
    >>> node.write(sys.stdout)
    N"None"
    P"TestSignal1"C
    R"TestSignal2"S
    """
    def __init__(self,name=None):
        self.name=name
        self.isFinalized = False
        self.dataTypes = []
        self.requirePorts=[]
        self.providePorts=[]
        self.dataTypeMap = {}


    @classmethod
    def from_autosar_swc(cls, swc, name=None, reverse=False):
        assert(isinstance(swc, autosar.component.AtomicSoftwareComponent))
        node = cls()
        node.import_autosar_swc(swc, name=name)
        return node

    @classmethod
    def from_text(cls, text):
        return Parser().loads(text)

    def _updateDataType(self, ws, port):
        portInterface = ws.find(port.portInterfaceRef)
        if isinstance(portInterface,autosar.portinterface.SenderReceiverInterface):
            if len(portInterface.dataElements)==1:
                dataType = ws.find(portInterface.dataElements[0].typeRef)
                assert(dataType is not None)
                if dataType.name not in self.dataTypeMap:
                    item = apx.AutosarDataType(ws,dataType, self)
                    item.id=len(self.dataTypes)
                    self.dataTypeMap[dataType.name]=item
                    self.dataTypes.append(item)
                    assert (item is not None)
                    return item
                else:
                    item = self.dataTypeMap[dataType.name]
                    assert (item is not None)
                    return item
            elif len(portInterface.dataElements)>1:
                raise NotImplementedError('SenderReceiverInterface with more than 1 element not supported')
        return None

    def _calcAttributeFromAutosarPort(self,ws,port):
        """
        returns string
        """
        if (len(port.comspec)==1) and isinstance(port.comspec[0],autosar.port.DataElementComSpec):
            if port.comspec[0].initValueRef is not None:
                initValue = ws.find(port.comspec[0].initValueRef)
                if initValue is None:
                    raise ValueError('invalid init value reference: '+port.comspec[0].initValueRef)
                if isinstance(initValue, autosar.constant.Constant):
                    initValue=initValue.value
                return "="+self._deriveInitValueFromAutosarConstant(initValue)
        return None

    def _deriveInitValueFromAutosarConstant(self,item):
        if isinstance(item,autosar.constant.IntegerValue):
            if (item.value>255):
                return "0x%02X"%item.value
            else:
                return "%d"%item.value
        elif isinstance(item,autosar.constant.StringValue):
            return '"%s"'%item.value
        elif isinstance(item,autosar.constant.RecordValue):
            tmp = [self._deriveInitValueFromAutosarConstant(x) for x in item.elements]
            return "{"+','.join(tmp)+"}"
        elif isinstance(item,autosar.constant.ArrayValue):
            tmp = [self._deriveInitValueFromAutosarConstant(x) for x in item.elements]
            return "{"+','.join(tmp)+"}"
        else:
            raise NotImplementedError(str(type(item)))


    def import_autosar_swc(self, swc, ws=None, name=None):
        assert(isinstance(swc, autosar.component.AtomicSoftwareComponent))
        if name is None:
            self.name=swc.name
        else:
            self.name = name
        if ws is None:
            ws=swc.rootWS()
        for port in swc.providePorts:
            self.add_autosar_port(port, ws)
        for port in swc.requirePorts:
            self.add_autosar_port(port, ws)
        self.resolve_types()
        return self

    def add_autosar_port(self, port, ws=None):
        """
        adds an autosar port to the node
        returns the port ID of the newly added port
        """
        if ws is None:
            ws=port.rootWS()
        assert(ws is not None)
        dataType=self._updateDataType(ws, port)
        if dataType is not None:
            if isinstance(port, autosar.port.RequirePort):
                apx_port = apx.RequirePort(port.name, "T[%s]"%dataType.id, self._calcAttributeFromAutosarPort(ws, port))
                return self.add_require_port(apx_port)
            elif isinstance(port, autosar.port.ProvidePort):
                apx_port = apx.ProvidePort(port.name, "T[%s]"%dataType.id, self._calcAttributeFromAutosarPort(ws, port))
                return self.add_provide_port(apx_port)
            else:
                raise ValueError('invalid type '+str(type(port)))

    def append(self, item):
        """
        Adds the item to the node.
        Item can be of type DataType, RequirePort and ProvidePort
        returns the object (port or datatype)
        """
        if isinstance(item, apx.DataType):
            return self.add_type(item)
        if isinstance(item, apx.RequirePort):
            return self.add_require_port(item)
        elif isinstance(item, apx.ProvidePort):
            return self.add_provide_port(item)
        elif isinstance(item, autosar.port.Port):
            return self.add_autosar_port(item)
        elif isinstance(item, str):
            parts = apx_split_line(item)
            if len(parts) != 4:
                raise ValueError("invalid APX string: '%s'"%item)
            if parts[0]=='R':
                newPort = apx.RequirePort(parts[1],parts[2],parts[3])
                if newPort is not None:
                    return self.add_require_port(newPort)
                else:
                    raise ValueError('apx.RequirePort() returned None')
            elif parts[0]=='P':
                newPort = apx.ProvidePort(parts[1],parts[2],parts[3])
                if newPort is not None:
                    return self.add_provide_port(newPort)
                else:
                    raise ValueError('apx.ProvidePort() returned None')
            else:
                raise ValueError(parts[0])
        else:
            raise ValueError(type(item))


    def add_type(self, new_type):
        if new_type.name not in self.dataTypeMap:
            new_type.dsg.resolve_data_element(self.dataTypes)
            self.dataTypeMap[new_type.name]=new_type
            self.dataTypes.append(new_type)
            return new_type
        else:
            existing_type = self.dataTypeMap[new_type.name]
            self._verify_data_types_are_equal(existing_type, new_type)
            return existing_type

    def extend(self, other_node):
        """
        Copies all port from other_node and adds them to this node
        """
        for port in other_node.requirePorts+other_node.providePorts:
            self.add_port_from_node(other_node, port)
        return self

    def add_require_port(self, port):
        port.id = len(self.requirePorts)
        if port.dsg.dataElement.isReference:
            port.resolve_type(self.dataTypes)
        self.requirePorts.append(port)
        return port

    def add_provide_port(self, port):
        port.id = len(self.providePorts)
        if port.dsg.dataElement.isReference:
            port.resolve_type(self.dataTypes)
        self.providePorts.append(port)
        return port

    def save_apx(self, output_dir='.', output_file = None, normalized=False):
        """
        Saves node in the .apx file format
        If normalized is True it uses the traditional type reference by ID.
        If normalized is False it uses the newer type reference by name which is not fully supported yet by all clients.
        If output_file is None (default) it generates a file based on the node name.
        If output_file is None it generates the file in output_dir (defaults to current directory)
        """
        if not self.isFinalized:
            self.finalize_sorted()
        if output_file is None:
            output_file = os.path.normpath(os.path.join(output_dir, self.name+'.apx'))
        with open(output_file, "w", newline='\n') as fp:
            fp.write("APX/1.2\n") #APX Text header
            self.write(fp, normalized)
            fp.write("\n") #Add extra newline at end of file

    def save_apx_normalized(self, output_dir='.', output_file = None):
        self.save_apx(output_dir, output_file, True)

    def dumps(self, normalized=False):
        if not self.isFinalized:
            self.finalize_sorted()
        lines = self.lines(normalized)
        text = 'APX/1.2\n'+'\n'.join(lines)+'\n'
        return text

    def dumps_normalized(self):
        return self.dumps(True)

    def write(self, fp, normalized=False):
        """
        writes node as text in fp
        """
        print('N"%s"'%self.name, file=fp)
        for dataType in self.dataTypes:
            print(str(dataType), file=fp)
        for port in self.providePorts:
            print(port.to_string(normalized), file=fp)
        for port in self.requirePorts:
            print(port.to_string(normalized), file=fp)

    def lines(self, normalized=False):
        """
        returns node as list of strings (one line at a time)
        """
        lines = ['N"%s"'%self.name]
        for dataType in self.dataTypes:
            lines.append(str(dataType))
        for port in self.providePorts:
            lines.append(port.to_string(normalized))
        for port in self.requirePorts:
            lines.append(port.to_string(normalized))
        return lines

    def mirror(self, name=None):
        """
        clones the node in a version where all provide and require ports are reversed
        """
        if name is None:
            name = self.name
        mirror = Node(name)
        mirror.dataTypes = deepcopy(self.dataTypes)
        mirror.requirePorts = [port.mirror() for port in self.providePorts]
        mirror.providePorts = [port.mirror() for port in self.requirePorts]
        for dataType in mirror.dataTypes:
            mirror.dataTypeMap[dataType.name]=dataType
        mirror.resolve_types()
        return mirror

    def add_port_from_node(self, from_node, from_port, ignore_duplicates=False):
        """
        Attempts to clone the port from the other node, including all its data types
        If a port with from_port.name already exists it is ignored if ignore_duplicates is True,
        otherwise it generates an error.
        """

        if not isinstance(from_node, apx.Node):
            raise ValueError('from_node argument must be of type apx.Node')
        if not isinstance(from_port, apx.Port):
            raise ValueError('from_node argument must derive from type apx.Port')

        port_list = self.providePorts if isinstance(from_port, apx.ProvidePort) else self.requirePorts
        existing_port = self._check_duplicate_port(from_port)
        if existing_port is not None:
            return existing_port

        to_port = from_port.clone()
        from_data_element = from_port.dsg.dataElement
        if from_data_element.typeCode == apx.REFERENCE_TYPE_CODE:
            from_data_type = from_data_element.typeReference
            if not isinstance(from_data_type, apx.base.DataType):
                raise RuntimeError('Node.finalize() method must be called before this method can be used')
            to_data_type = self.find(from_data_type.name)
            if to_data_type is None:
                to_data_type = self.add_data_type_from_node(from_node, from_data_type)
            else:
                self._verify_data_types_are_equal(to_data_type, from_data_type)
            to_port.dsg.dataElement.typeReference = to_data_type
        self.append(to_port)
        return to_port

    def add_data_type_from_node(self, from_node, from_data_type):
        """
        Attempts to clone the data type from other node to this node
        """
        if not isinstance(from_node, apx.Node):
            raise ValueError('from_node argument must be of type apx.Node')

        if not isinstance(from_data_type, apx.DataType):
            raise ValueError('from_data_type argument must be of type apx.DataType')
        from_data_element = from_data_type.dsg.dataElement
        if (from_data_element.typeCode >= apx.UINT8_TYPE_CODE) and (from_data_element.typeCode < apx.RECORD_TYPE_CODE):
            pass #no further action needed
        elif (from_data_element.typeCode == apx.RECORD_TYPE_CODE):
            for elem in from_data_element.elements:
                if elem.typeCode == apx.REFERENCE_TYPE_CODE:
                    self.add_data_type_from_node(from_node, elem.typeReference)
        else:
            raise NotImplementedError(from_data_element.typeCode)

        to_data_type = from_data_type.clone()
        self.append(to_data_type)
        return to_data_type

    def find(self, name):
        """
        Finds type or port by name.
        If the variable name is a list, it finds multiple items
        """
        if isinstance(name, list):
            result = []
            for inner_name in name:
                result.append(self._inner_find(inner_name))
            return result
        else:
            return self._inner_find(name)

    def _inner_find(self, name):
        """
        finds type or port by name (internal implementation)
        """
        for elem in self.dataTypes+self.requirePorts+self.providePorts:
            if elem.name == name:
                return elem

    def resolve_types(self):
        """
        Resolves all integer and string type references with their actual object counter-parts
        """
        for port in self.requirePorts+self.providePorts:
            if port.dsg.dataElement.isReference:
                port.resolve_type(self.dataTypes)

    def finalize(self, sort=False):
        if not self.isFinalized:
            self.resolve_types()
            self._sort_elements(sort)
            self._set_type_ids()
            self.isFinalized = True
            return self

    def finalize_sorted(self):
        return self.finalize(sort=True)

    def _verify_data_types_are_equal(self, existing_type, new_type):
        existing_type_signature = existing_type.to_string(normalized=True)
        new_type_signature = new_type.to_string(normalized=True)
        if existing_type_signature != new_type_signature:
            raise ValueError("Data type '{}' already exist but with different signature\nExpected: {}\nGot: {}".format(existing_type.name, existing_type_signature, new_type_signature))

    def _check_duplicate_port(self, new_port):
        for existing_port in self.providePorts+self.requirePorts:
            if existing_port.name == new_port.name:
                if isinstance(existing_port, apx.RequirePort) and isinstance(new_port, apx.ProvidePort):
                    raise ValueError("Cannot add provide-port with same name. Port '{}' already exists as require-port.".format(new_port.name))
                elif isinstance(existing_port, apx.ProvidePort) and isinstance(new_port, apx.RequirePort):
                    raise ValueError("Cannot add require-port with same name. Port '{}' already exists as provide-port.".format(new_port.name))
                else:
                    self._verify_ports_are_equal(existing_port, new_port)
                    return existing_port
        return None

    def _verify_ports_are_equal(self, existing_port, new_port):
        existing_port_signature = existing_port.to_string(normalized=True)
        new_port_signature = new_port.to_string(normalized=True)
        if existing_port_signature != new_port_signature:
            raise ValueError("Port '{}' already exist but with different signature\nExpected: {}\nGot: {}".format(existing_port.name, existing_port_signature, new_port_signature))

    def _sort_elements(self, sort_all):
        kfunc = lambda x: x.name
        if len(self.dataTypes) > 0:
            self.dataTypes = sorted(self.dataTypes, key=kfunc)
        if sort_all:
            if len(self.requirePorts) > 0:
                self.requirePorts = sorted(self.requirePorts, key=kfunc)
            if len(self.providePorts) > 0:
                self.providePorts = sorted(self.providePorts, key=kfunc)

    def _set_type_ids(self):
        for i,data_type in enumerate(self.dataTypes):
            data_type.id = i
