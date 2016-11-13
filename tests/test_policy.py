import unittest
import os

from britney2 import SuiteInfo, SourcePackage
from britney2.excuse import Excuse
from britney2.hints import HintParser
from britney2.policies.policy import RCBugPolicy, PolicyVerdict

POLICY_DATA_BASE_DIR = os.path.join(os.path.dirname(__file__), 'policy-test-data')
TEST_HINTER = 'test-hinter'
HINTS_ALL = ('ALL')


def initialize_policy(test_name, policy_class, *args, **kwargs):
    test_dir = os.path.join(POLICY_DATA_BASE_DIR, test_name)
    hints = []
    if 'hints' in kwargs:
        hints = kwargs['hints']
        del kwargs['hints']
    options = MockObject(state_dir=test_dir, verbose=0, **kwargs)
    suite_info = {
        'testing': SuiteInfo('testing', os.path.join(test_dir, 'testing'), ''),
        'unstable': SuiteInfo('unstable', os.path.join(test_dir, 'unstable'), ''),
    }
    policy = policy_class(options, suite_info, *args)
    fake_britney = MockObject(log=lambda x, y='I': None)
    hint_parser = HintParser(fake_britney)
    policy.initialise(fake_britney)
    policy.register_hints(hint_parser)
    hint_parser.parse_hints(TEST_HINTER, HINTS_ALL, 'test-%s' % test_name, hints)
    policy.hints = hint_parser.hints
    return policy


def create_excuse(name):
    return Excuse(name)


def create_source_package(version, section='devel', binaries=None):
    if binaries is None:
        binaries = []
    return SourcePackage(version, section, binaries, 'Random tester', False)


def create_policy_objects(source_name, target_version, source_version):
    return (
        create_source_package(target_version),
        create_source_package(source_version),
        create_excuse(source_name),
        {},
    )


class MockObject(object):

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class TestRCBugsPolicy(unittest.TestCase):

    def test_no_bugs(self):
        src_name = 'has-no-bugs'
        src_t, src_u, excuse, policy_info = create_policy_objects(src_name, '1.0', '2.0')
        policy = initialize_policy('rc-bugs/basic', RCBugPolicy)
        verdict = policy.apply_policy(policy_info, 'unstable', src_name, src_t, src_u, excuse)
        assert verdict == PolicyVerdict.PASS
        assert set(policy_info['rc-bugs']['unique-source-bugs']) == set()
        assert set(policy_info['rc-bugs']['unique-target-bugs']) == set()
        assert set(policy_info['rc-bugs']['shared-bugs']) == set()

    def test_regression(self):
        src_name = 'regression'
        src_t, src_u, excuse, policy_info = create_policy_objects(src_name, '1.0', '2.0')
        policy = initialize_policy('rc-bugs/basic', RCBugPolicy)
        verdict = policy.apply_policy(policy_info, 'unstable', src_name, src_t, src_u, excuse)
        assert verdict == PolicyVerdict.REJECTED_PERMANENTLY
        assert set(policy_info['rc-bugs']['unique-source-bugs']) == {'123458'}
        assert set(policy_info['rc-bugs']['unique-target-bugs']) == set()
        assert set(policy_info['rc-bugs']['shared-bugs']) == set()

    def test_regression_but_fixes_more_bugs(self):
        src_name = 'regression-but-fixes-more-bugs'
        src_t, src_u, excuse, policy_info = create_policy_objects(src_name, '1.0', '2.0')
        policy = initialize_policy('rc-bugs/basic', RCBugPolicy)
        verdict = policy.apply_policy(policy_info, 'unstable', src_name, src_t, src_u, excuse)
        assert verdict == PolicyVerdict.REJECTED_PERMANENTLY
        assert set(policy_info['rc-bugs']['unique-source-bugs']) == {'100003'}
        assert set(policy_info['rc-bugs']['unique-target-bugs']) == {'100001', '100002'}
        assert set(policy_info['rc-bugs']['shared-bugs']) == {'100000'}

    def test_not_a_regression(self):
        src_name = 'not-a-regression'
        src_t, src_u, excuse, policy_info = create_policy_objects(src_name, '1.0', '2.0')
        policy = initialize_policy('rc-bugs/basic', RCBugPolicy)
        verdict = policy.apply_policy(policy_info, 'unstable', src_name, src_t, src_u, excuse)
        assert verdict == PolicyVerdict.PASS
        assert set(policy_info['rc-bugs']['unique-source-bugs']) == set()
        assert set(policy_info['rc-bugs']['unique-target-bugs']) == set()
        assert set(policy_info['rc-bugs']['shared-bugs']) == {'123457'}

    def test_improvement(self):
        src_name = 'fixes-bug'
        src_t, src_u, excuse, policy_info = create_policy_objects(src_name, '1.0', '2.0')
        policy = initialize_policy('rc-bugs/basic', RCBugPolicy)
        verdict = policy.apply_policy(policy_info, 'unstable', src_name, src_t, src_u, excuse)
        assert verdict == PolicyVerdict.PASS
        assert set(policy_info['rc-bugs']['unique-source-bugs']) == set()
        assert set(policy_info['rc-bugs']['unique-target-bugs']) == {'123456'}
        assert set(policy_info['rc-bugs']['shared-bugs']) == set()

    def test_regression_with_hint(self):
        src_name = 'regression'
        hints = ['ignore-rc-bugs 123458 regression/2.0']
        src_t, src_u, excuse, policy_info = create_policy_objects(src_name, '1.0', '2.0')
        policy = initialize_policy('rc-bugs/basic', RCBugPolicy, hints=hints)
        verdict = policy.apply_policy(policy_info, 'unstable', src_name, src_t, src_u, excuse)
        assert verdict == PolicyVerdict.PASS_HINTED
        assert set(policy_info['rc-bugs']['ignored-bugs']['bugs']) == {'123458'}
        assert policy_info['rc-bugs']['ignored-bugs']['issued-by'] == TEST_HINTER
        assert set(policy_info['rc-bugs']['unique-source-bugs']) == set()
        assert set(policy_info['rc-bugs']['unique-target-bugs']) == set()
        assert set(policy_info['rc-bugs']['shared-bugs']) == set()

    def test_regression_but_fixes_more_bugs_bad_hint(self):
        src_name = 'regression-but-fixes-more-bugs'
        hints = ['ignore-rc-bugs 100000 regression-but-fixes-more-bugs/2.0']
        src_t, src_u, excuse, policy_info = create_policy_objects(src_name, '1.0', '2.0')
        policy = initialize_policy('rc-bugs/basic', RCBugPolicy, hints=hints)
        verdict = policy.apply_policy(policy_info, 'unstable', src_name, src_t, src_u, excuse)
        assert verdict == PolicyVerdict.REJECTED_PERMANENTLY
        print(str(policy_info['rc-bugs']))
        assert set(policy_info['rc-bugs']['unique-source-bugs']) == {'100003'}
        assert set(policy_info['rc-bugs']['unique-target-bugs']) == {'100001', '100002'}
        assert set(policy_info['rc-bugs']['ignored-bugs']['bugs']) == {'100000'}
        assert policy_info['rc-bugs']['ignored-bugs']['issued-by'] == TEST_HINTER
        assert set(policy_info['rc-bugs']['shared-bugs']) == set()

if __name__ == '__main__':
    unittest.main()
