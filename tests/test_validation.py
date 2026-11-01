import os
import shutil
import subprocess
import unittest
from unittest.mock import Mock, patch

from ai_agent.validation import validate


class ValidationTests(unittest.TestCase):
    def test_python_checks_syntax_without_execution(self):
        self.assertEqual(validate("raise RuntimeError('must not run')", "test.py").status, "passed")
        self.assertEqual(validate("def broken(\n", "test.py").status, "failed")
        self.assertEqual(validate("return 1", "test.py").status, "failed")

    def test_json_accepts_valid_and_rejects_invalid_constants(self):
        self.assertEqual(validate('{"ready":true}', "test.json").status, "passed")
        for source in ('{"ready":}', '{"value":NaN}', '{"value":Infinity}'):
            with self.subTest(source=source):
                self.assertEqual(validate(source, "test.json").status, "failed")

    def test_missing_compiler_is_unavailable(self):
        with patch("ai_agent.validation.shutil.which", return_value=None):
            self.assertEqual(validate("class Test {}", "Test.java").status, "unavailable")

    def test_java_isolated_compiler_options_and_environment(self):
        with patch("ai_agent.validation.shutil.which", return_value="javac"), \
                patch.dict(os.environ, {"JDK_JAVAC_OPTIONS": "-processor Bad", "JAVA_TOOL_OPTIONS": "-javaagent:bad.jar"}), \
                patch("ai_agent.validation.subprocess.run", return_value=Mock(returncode=0)) as run:
            self.assertEqual(validate("class Test {}", "Test.java").status, "passed")
            args = run.call_args.args[0]
            self.assertIn("-proc:none", args)
            self.assertIn("-sourcepath", args)
            self.assertIn("-classpath", args)
            self.assertNotIn("JAVA_TOOL_OPTIONS", run.call_args.kwargs["env"])
            self.assertNotIn("JDK_JAVAC_OPTIONS", run.call_args.kwargs["env"])
            self.assertEqual(run.call_args.kwargs["timeout"], 20)

    def test_compiler_timeout_is_unavailable(self):
        with patch("ai_agent.validation.shutil.which", return_value="javac"), \
                patch("ai_agent.validation.subprocess.run", side_effect=subprocess.TimeoutExpired("javac", 20)):
            self.assertEqual(validate("class Test {}", "Test.java").status, "unavailable")

    @unittest.skipUnless(shutil.which("javac"), "JDK not installed")
    def test_real_java_valid_invalid_and_missing_dependency(self):
        for content, expected in (("public class Test { static int x = 1; }", "passed"),
                                  ("public class Test { int x = ; }", "failed"),
                                  ("public class Test { MissingDependency x; }", "failed")):
            with self.subTest(content=content):
                result = validate(content, "Test.java")
                self.assertEqual(result.status, expected, result.detail)
