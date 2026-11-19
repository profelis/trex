import contextlib
import importlib.machinery
import importlib.util
import io
import itertools
import json
from types import SimpleNamespace
from pathlib import Path
import unittest
from unittest.mock import patch

loader = importlib.machinery.SourceFileLoader('trex', str(Path(__file__).resolve().parents[1] / 'trex'))
spec = importlib.util.spec_from_loader(loader.name, loader)
trex = importlib.util.module_from_spec(spec)
loader.exec_module(trex)


class AgentTests(unittest.TestCase):
    def test_interactive_auto_with_model_and_access(self):
        cmd, env = trex.spawn_command('vibe', 'auto', model='test-model',
                                      dirs=['/private/tmp/shared'], prompt='Review this')
        self.assertEqual(cmd, ['vibe', '--trust', '--smart-approve', '--add-dir',
                               '/private/tmp/shared', 'Review this'])
        self.assertEqual(env, {'VIBE_ACTIVE_MODEL': 'test-model'})

    def test_own_and_full_modes(self):
        self.assertEqual(trex.spawn_command('vibe', 'own'), (['vibe'], {}))
        self.assertEqual(trex.spawn_command('vibe', 'full'),
                         (['vibe', '--trust', '--auto-approve'], {}))

    def test_headless_only_effort_is_refused(self):
        with contextlib.redirect_stderr(io.StringIO()) as err:
            with self.assertRaises(SystemExit) as result:
                trex.spawn_command('vibe', 'auto', effort='high')
        self.assertEqual(result.exception.code, 2)
        self.assertIn('interactive startup', err.getvalue())

    def test_native_process_and_statuses(self):
        for name, agent in [('claude', 'claude'), ('codex', 'codex'),
                            ('opencode', 'opencode'), ('vibe', 'vibe'),
                            ('vibe-rs', 'vibe')]:
            for state, kind in [('idle', ''), ('working', ''), ('done', ''),
                                ('blocked', 'permission'), ('error', '')]:
                with self.subTest(name=name, state=state):
                    def response(*args, **kwargs):
                        if args[-1] == 'process':
                            return {'foreground': {'name': name, 'cwd': '/tmp'}}
                        if args[-1] == 'program_status':
                            return {'records': [{'state': state, 'kind': kind,
                                                  'title': 'Vibe test'}]}
                        return {}
                    with patch.object(trex, 'rex_json', side_effect=response):
                        result = trex.inspect({'session_id': 's'}, {'block_id': 'b'})
                    self.assertEqual(result['kind'], agent)
                    self.assertEqual(result['state'], state)
                    self.assertEqual(result['state_kind'], kind)

    def test_process_ancestor_is_recognized_during_tool_execution(self):
        for name, agent in [('claude', 'claude'), ('codex', 'codex'),
                            ('opencode', 'opencode'), ('vibe-rs', 'vibe')]:
            with self.subTest(agent=agent):
                def response(*args, **kwargs):
                    if args[-1] == 'process':
                        return {'foreground': {'name': 'bash'},
                                'ancestors': [{'name': name}]}
                    return {'records': [{'state': 'working', 'title': 'Tool running'}]}
                with patch.object(trex, 'rex_json', side_effect=response):
                    result = trex.inspect({'session_id': 's'}, {'block_id': 'b'})
                self.assertEqual(result['kind'], agent)
                self.assertEqual(result['state'], 'working')

    def test_existing_agent_permission_modes(self):
        cases = {
            'claude': (['claude'], ['--permission-mode', 'auto'],
                       ['--dangerously-skip-permissions']),
            'codex': (['codex', '-c', 'sandbox_workspace_write.network_access=true'],
                      ['--approve-for-me'], ['--dangerously-bypass-approvals-and-sandbox']),
            'opencode': (['opencode'], ['--auto'], ['--auto']),
        }
        for agent, (base, auto, full) in cases.items():
            for mode, flags in [('own', []), ('auto', auto), ('full', full)]:
                with self.subTest(agent=agent, mode=mode):
                    self.assertEqual(trex.spawn_command(agent, mode), (base + flags, {}))

    def test_claude_model_effort_and_repeated_directories(self):
        cmd, env = trex.spawn_command('claude', 'auto', model='opus', effort='high',
                                      dirs=['one', 'two'], prompt='Review this')
        self.assertEqual(cmd, ['claude', '--permission-mode', 'auto', '--model', 'opus',
                               '--effort', 'high', '--add-dir', str(Path('one').resolve()),
                               '--add-dir', str(Path('two').resolve()), 'Review this'])
        self.assertEqual(env, {})

    def test_codex_keeps_socket_access_with_model_and_effort(self):
        cmd, env = trex.spawn_command('codex', 'auto', model='gpt-5', effort='high',
                                      dirs=['shared'], prompt='Review this')
        self.assertEqual(cmd, ['codex', '-c', 'sandbox_workspace_write.network_access=true',
                               '--approve-for-me', '--model', 'gpt-5', '-c',
                               'model_reasoning_effort=high', '--add-dir',
                               str(Path('shared').resolve()), 'Review this'])
        self.assertEqual(env, {})

    def test_opencode_model_gets_own_server_and_prompt_flag(self):
        cmd, env = trex.spawn_command('opencode', 'auto', model='provider/model#variant',
                                      prompt='Review this')
        self.assertEqual(cmd, ['opencode', '--auto', '--standalone', '--prompt', 'Review this'])
        self.assertEqual(json.loads(env['OPENCODE_CONFIG_CONTENT']),
                         {'model': 'provider/model#variant'})

    def test_opencode_refuses_unsupported_options(self):
        for option in [{'effort': 'high'}, {'dirs': ['shared']}]:
            with self.subTest(option=option), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as result:
                    trex.spawn_command('opencode', 'auto', **option)
                self.assertEqual(result.exception.code, 2)

    def test_unrelated_process_is_not_an_agent(self):
        with patch.object(trex, 'rex_json', return_value={'foreground': {'name': 'python'}}):
            self.assertIsNone(trex.inspect({'session_id': 's'}, {'block_id': 'b'}))

    def test_wait_distinguishes_completion_and_attention(self):
        for agent in ['claude', 'codex', 'opencode', 'vibe']:
            for state, kind, code in [('done', '', 0), ('idle', '', 0),
                                      ('blocked', 'permission', 3), ('error', '', 3)]:
                with self.subTest(agent=agent, state=state):
                    target = {'name': agent, 'kind': agent, 'session': 's', 'block': 'b'}
                    states = [{'state': 'working'}, {'state': state, 'state_kind': kind}]
                    with patch.object(trex, 'inspect', side_effect=states), \
                            patch.object(trex.time, 'time', side_effect=itertools.count()), \
                            patch.object(trex, 'WAIT_POLL', 0), \
                            contextlib.redirect_stdout(io.StringIO()) as output:
                        result = trex.wait_for(target, 100, None)
                    self.assertEqual(result, code)
                    self.assertEqual(output.getvalue().strip(), state + (':' + kind if kind else ''))

    def test_send_never_answers_a_permission_prompt(self):
        for agent in ['claude', 'codex', 'opencode', 'vibe']:
            with self.subTest(agent=agent):
                target = {'name': agent, 'kind': agent, 'session': 's', 'block': 'b',
                          'state': 'blocked', 'state_kind': 'permission'}
                args = SimpleNamespace(target=agent, text=['Hello'], reply=False, fyi=False)
                with patch.object(trex, 'resolve', return_value=target), \
                        patch.object(trex, 'me', return_value=None), \
                        patch.object(trex, 'is_root', return_value=False), \
                        patch.object(trex, 'rex') as rex, \
                        contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as result:
                        trex.cmd_send(args)
                    self.assertEqual(result.exception.code, 2)
                    rex.assert_not_called()


if __name__ == '__main__':
    unittest.main()
