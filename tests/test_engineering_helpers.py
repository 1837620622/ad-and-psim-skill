"""以解析关系核对测量与连接检查，不依赖本机客户工程。"""
from pathlib import Path
import math
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'skills/ad-schematic-layout/scripts'),str(ROOT/'skills/psim-simulation-layout/scripts')]
from compare_pin_nets import compare,load_pin_map  # noqa: E402
from analyze_waveform import load_csv,measure,moments,mean_product,clip,gate_frequency  # noqa: E402


class Measurements(unittest.TestCase):
    def test_nonuniform_integral_and_product(self):
        t=[0.,.1,1.];v=[0.,.1,1.]
        self.assertAlmostEqual(moments(t,v)['mean'],.5)
        self.assertAlmostEqual(moments(t,v)['rms'],math.sqrt(1/3))
        self.assertAlmostEqual(mean_product(t,v,v),1/3)
        x,y=clip(t,{'x':v},.25,.75)
        self.assertAlmostEqual(moments(x,y['x'])['mean'],.5)

    def test_no_false_steady_efficiency_or_dc_pf(self):
        t=[0.,1.,2.];d={'vin':[10.]*3,'iin':[1.]*3,'vo':[5.]*3,'io':[1.]*3}
        result=measure(t,d,vin='vin',iin='iin',vout='vo',iout='io')
        self.assertEqual(result['power_ratio_percent'],50)
        self.assertIsNone(result['efficiency_percent'])
        self.assertNotIn('input_total_power_factor',result)
        self.assertEqual(measure(t,d,vin='vin',iin='iin',vout='vo',iout='io',steady=True)['efficiency_percent'],50)

    def test_ac_pf_requires_complete_window(self):
        t=[i/1000 for i in range(41)]
        sine=[math.sin(2*math.pi*50*x)for x in t]
        data={'v':sine,'i':sine,'po':[0.]*len(t)}
        result=measure(t,data,vin='v',iin='i',vout='v',iout='i',ac_input=True,fundamental=50)
        self.assertAlmostEqual(result['input_total_power_factor'],1.)
        with self.assertRaises(ValueError):measure(t,data,vin='v',iin='i',vout='v',iout='i',ac_input=True,fundamental=50,start=.001)

    def test_energy_and_gate(self):
        t=[0.,1.];d={'pin':[1.,1.],'pout':[0.,0.],'vc':[0.,2.]}
        result=measure(t,d,pin='pin',pout='pout',capacitors=[('vc',.5)])
        self.assertAlmostEqual(result['known_storage_power_W'],1.)
        self.assertAlmostEqual(result['residual_after_known_storage_W'],0.)
        t=[i*.001 for i in range(11)];v=[i%2 for i in range(11)]
        self.assertAlmostEqual(gate_frequency(t,v,.5)['average_hz'],500.)

    def test_reject_bad_csv(self):
        with tempfile.TemporaryDirectory()as folder:
            path=Path(folder)/'bad.csv'
            for content in ['Time,V\n0,1\n0,2\n','Time,V\n0,1\n1,nan\n','Time,X\n0,1\n1,2\n']:
                path.write_text(content,encoding='utf-8')
                with self.assertRaises(ValueError):load_csv(path,['V'])


class NativeTopology(unittest.TestCase):
    def test_renamed_nets_and_break(self):
        expected={'U1.1':'A','R1.1':'A','R1.2':'B'}
        self.assertTrue(compare(expected,{'U1.1':'X','R1.1':'X','R1.2':'Y'})['match'])
        self.assertFalse(compare(expected,{'U1.1':'X','R1.1':'Z','R1.2':'Y'})['match'])
        self.assertFalse(compare(expected,{'U1.1':'X','R1.1':'X'})['match'])

    def test_duplicate_pin_detected_in_both_formats(self):
        with tempfile.TemporaryDirectory()as folder:
            path=Path(folder)/'nets.txt'
            for content in ['A|U1|1\nB|U1|1\n','{"pin_map":{"U1.1":"A","U1.1":"B"}}']:
                path.write_text(content,encoding='utf-8')
                with self.assertRaises(ValueError):load_pin_map(path)



if __name__=='__main__':unittest.main(verbosity=2)
