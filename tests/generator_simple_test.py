import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import apx
import unittest
import time
import shutil

class TestApxGenerator(unittest.TestCase):

    def test_code_generator(self):
        node = apx.Node("TestSimple")
        node.append(apx.RequirePort('RS32Port','l','=-2147483648'))
        node.append(apx.RequirePort('RU8Port','C','=255'))
        node.append(apx.RequirePort('PS16ARPort256','s[256]'))
        node.append(apx.ProvidePort('PS16ARPort256','s[256]'))
        node.append(apx.ProvidePort('PS8Port','c','=-1'))
        node.append(apx.ProvidePort('PU32Port','L','=4294967295'))

        output_dir = 'derived'
        output_dir_full = os.path.join(os.path.dirname(__file__),output_dir)
        if not os.path.exists(output_dir_full):
            os.makedirs(output_dir_full)
        time.sleep(0.1)
        apx.NodeGenerator().generate(output_dir_full, node)
        with open (os.path.join(os.path.dirname(__file__), output_dir, 'ApxNode_{0.name}.h'.format(node)), "r") as fp:
            generated=fp.read()
        with open (os.path.join(os.path.dirname(__file__), 'expected_gen', 'ApxNode_{0.name}.h'.format(node)), "r") as fp:
            expected=fp.read()
        self.assertEqual(expected, generated)
        with open (os.path.join(os.path.dirname(__file__), output_dir, 'ApxNode_{0.name}.c'.format(node)), "r") as fp:
            generated=fp.read()
        with open (os.path.join(os.path.dirname(__file__), 'expected_gen', 'ApxNode_{0.name}.c'.format(node)), "r") as fp:
            expected=fp.read()
        self.assertEqual(expected, generated)
        shutil.rmtree(output_dir_full)

if __name__ == '__main__':
    unittest.main()
