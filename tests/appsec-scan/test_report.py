"""Unit tests of appsec-scan report.py on saved opengrep/trivy JSON. No network; standard library only.

    python3 -m unittest discover -s tests/appsec-scan -p 'test_*.py' -v
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "plugins", "appsec-scan", "skills", "appsec-scan", "lib"))
import report  # noqa: E402

ALL_OK = ["base", "sast", "sast-base", "sca", "sca-base", "sca-native", "sca-native-base"]


def finding(path, line, text, rule="rules.test-eval"):
    return {"check_id": rule, "path": path, "start": {"line": line},
            "extra": {"lines": text, "severity": "ERROR", "metadata": {"cwe": ["CWE-95: Eval Injection"]}}}


def vuln(pkg, ver, vid, pkg_id=None):
    v = {"PkgName": pkg, "InstalledVersion": ver, "VulnerabilityID": vid, "Severity": "HIGH", "FixedVersion": "9.9.9",
         "Title": f"{pkg} issue"}
    if pkg_id:
        v["PkgID"] = pkg_id
    return v


def trivy(*results):
    return {"SchemaVersion": 2, "Results": list(results)}


class Run:
    """A run directory with HEAD sources in repo/, base sources in base-src/ and the given artifacts."""

    def __init__(self, repo_name="repo"):
        self.dir = tempfile.mkdtemp(prefix="appsec-report-")
        self.repo = os.path.join(self.dir, repo_name)
        self.base = os.path.join(self.dir, "base-src")
        os.makedirs(self.repo)
        os.makedirs(self.base)
        self.statuses = {name: "ok" for name in ALL_OK}

    def source(self, where, rel, text):
        path = os.path.join(self.repo if where == "head" else self.base, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def json(self, name, data):
        path = os.path.join(self.dir, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def build(self):
        with open(os.path.join(self.dir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump({"REPO": self.repo, "NAME": "fixture", "BRANCH": "feature", "HEAD_SHA": "1234567890ab", "DIRTY": "0",
                       "BASE_REF": "main", "BASE_SHA": "abcdef123456", "LANGS": "python", "BUILD": "none",
                       "RULES": "registry"}, f)
        with open(os.path.join(self.dir, "status.tsv"), "w", encoding="utf-8") as f:
            for name, state in self.statuses.items():
                f.write(f"{name}\t{state}\t{name} {state} reason\n")
        report._source_cache.clear()
        return report.build(self.dir)

    def close(self):
        shutil.rmtree(self.dir)


class SastTest(unittest.TestCase):
    def setUp(self):
        self.run = Run()

    def tearDown(self):
        self.run.close()

    def sast(self, head_src, head_hits, base_src, base_hits):
        self.run.source("head", "app.py", head_src)
        self.run.source("base", "app.py", base_src)
        self.run.json("sast-head.json", {"results": [finding("app.py", ln, t) for ln, t in head_hits], "errors": []})
        self.run.json("sast-base.json", {"results": [finding("app.py", ln, t) for ln, t in base_hits], "errors": []})
        text, summary = self.run.build()
        found = summary["findings"]
        return text, sorted((x["status"], x["func"], x["line"]) for x in found["sast"]), \
            sorted((x["func"],) for x in found["sast_fixed"])

    def test_existing_new_and_fixed(self):
        base = "def keep(a):\n    return eval(a)\n\ndef drop(b):\n    return eval(b)\n"
        head = "def keep(a):\n    return eval(a)\n\ndef added(c):\n    return eval(c)\n"
        text, found, fixed = self.sast(head, [(2, "    return eval(a)"), (5, "    return eval(c)")],
                                       base, [(2, "    return eval(a)"), (5, "    return eval(b)")])
        self.assertEqual(found, [("existing", "keep", 2), ("new", "added", 5)])
        self.assertEqual(fixed, [("drop",)])
        self.assertIn("## SAST: 2 finding(s), new: 1", text)
        self.assertIn("Fixed in the branch (in the base, not in HEAD): 1", text)

    def test_rule_is_part_of_the_key(self):
        # same file, function and line text, another rule: the HEAD finding is new and the base one is fixed
        src = "def keep(a):\n    return eval(a)\n"
        self.run.source("head", "app.py", src)
        self.run.source("base", "app.py", src)
        self.run.json("sast-head.json", {"results": [finding("app.py", 2, "    return eval(a)", "rules.rule-b")], "errors": []})
        self.run.json("sast-base.json", {"results": [finding("app.py", 2, "    return eval(a)", "rules.rule-a")], "errors": []})
        _, summary = self.run.build()
        self.assertEqual([(x["status"], x["rule"], x["func"]) for x in summary["findings"]["sast"]],
                         [("new", "rules.rule-b", "keep")])
        self.assertEqual([(x["rule"], x["func"]) for x in summary["findings"]["sast_fixed"]], [("rules.rule-a", "keep")])

    @unittest.skipIf(os.name == "nt", "a newline is not allowed in a Windows path")
    def test_repo_path_with_newline(self):
        # meta.json keeps the repository root intact, so absolute HEAD paths match the base
        self.run.close()
        self.run = Run("re\npo")
        src = "def keep(a):\n    return eval(a)\n"
        self.run.source("head", "app.py", src)
        self.run.source("base", "app.py", src)
        self.run.json("sast-head.json", {"results": [finding(os.path.join(self.run.repo, "app.py"), 2, "    return eval(a)")],
                                         "errors": []})
        self.run.json("sast-base.json", {"results": [finding("app.py", 2, "    return eval(a)")], "errors": []})
        _, summary = self.run.build()
        self.assertEqual([(x["status"], x["file"]) for x in summary["findings"]["sast"]], [("existing", "app.py")])
        self.assertEqual(summary["findings"]["sast_fixed"], [])

    def test_same_line_in_two_functions(self):
        base = "def one(x):\n    return eval(x)\n"
        head = "def one(x):\n    return eval(x)\n\ndef two(x):\n    return eval(x)\n"
        _, found, fixed = self.sast(head, [(2, "    return eval(x)"), (5, "    return eval(x)")],
                                    base, [(2, "    return eval(x)")])
        self.assertEqual(found, [("existing", "one", 2), ("new", "two", 5)])
        self.assertEqual(fixed, [])

    def test_line_shift_is_existing(self):
        base = "def keep(a):\n    return eval(a)\n"
        head = "import os\n\n\n\n\ndef keep(a):\n    return eval(a)\n"
        _, found, fixed = self.sast(head, [(7, "    return eval(a)")], base, [(2, "    return eval(a)")])
        self.assertEqual(found, [("existing", "keep", 7)])
        self.assertEqual(fixed, [])

    def test_multiplicity(self):
        base = "def f(a):\n    eval(a)\n"
        head = "def f(a):\n    eval(a)\n    eval(a)\n"
        _, found, _ = self.sast(head, [(2, "    eval(a)"), (3, "    eval(a)")], base, [(2, "    eval(a)")])
        self.assertEqual(sorted(s for s, _, _ in found), ["existing", "new"])

    def test_base_unavailable_gives_unknown(self):
        self.run.statuses["sast-base"] = "fail"
        base = "def keep(a):\n    return eval(a)\n\ndef drop(b):\n    return eval(b)\n"
        text, found, fixed = self.sast(base, [(2, "    return eval(a)")], base,
                                       [(2, "    return eval(a)"), (5, "    return eval(b)")])
        self.assertEqual(found, [("?", "keep", 2)])
        self.assertEqual(fixed, [])
        self.assertIn("Comparison unavailable: base fail: sast-base fail reason", text)
        self.assertIn("new: ?", text)

    def test_head_failed_gives_unknown_and_no_fixed(self):
        self.run.statuses["sast"] = "fail"
        base = "def keep(a):\n    return eval(a)\n\ndef drop(b):\n    return eval(b)\n"
        text, found, fixed = self.sast(base, [(2, "    return eval(a)")], base,
                                       [(2, "    return eval(a)"), (5, "    return eval(b)")])
        self.assertEqual(found, [("?", "keep", 2)])
        self.assertEqual(fixed, [])
        self.assertNotIn("Fixed in the branch", text)
        self.assertIn("HEAD scan incomplete", text)


class ScaTest(unittest.TestCase):
    def setUp(self):
        self.run = Run()

    def tearDown(self):
        self.run.close()

    def test_same_cve_in_two_ecosystems(self):
        npm = {"Target": "package-lock.json", "Type": "npm", "Vulnerabilities": [vuln("lodash", "4.17.15", "CVE-2021-23337")]}
        yarn = {"Target": "web/yarn.lock", "Type": "yarn", "Vulnerabilities": [vuln("lodash", "4.17.15", "CVE-2021-23337")]}
        self.run.json("sca-native-head.json", trivy(npm, yarn))
        self.run.json("sca-native-base.json", trivy(npm))
        _, summary = self.run.build()
        got = sorted((x["status"], x["type"], x["target"]) for x in summary["findings"]["sca"])
        self.assertEqual(got, [("existing", "npm", "package-lock.json"), ("new", "yarn", "web/yarn.lock")])
        self.assertEqual(summary["findings"]["sca_fixed"], [])

    def test_fixed_and_new_package(self):
        base = {"Target": "go.mod", "Type": "gomod", "Vulnerabilities": [vuln("a", "1", "CVE-1"), vuln("b", "1", "CVE-2")]}
        head = {"Target": "go.mod", "Type": "gomod", "Vulnerabilities": [vuln("a", "1", "CVE-1"), vuln("c", "1", "CVE-3")]}
        self.run.json("sca-native-head.json", trivy(head))
        self.run.json("sca-native-base.json", trivy(base))
        text, summary = self.run.build()
        got = sorted((x["status"], x["pkg"], x["id"]) for x in summary["findings"]["sca"])
        self.assertEqual(got, [("existing", "a", "CVE-1"), ("new", "c", "CVE-3")])
        self.assertEqual([(x["pkg"], x["id"]) for x in summary["findings"]["sca_fixed"]], [("b", "CVE-2")])
        self.assertIn("Fixed in the branch: b CVE-2", text)

    def test_jvm_version_bump_with_same_cve_is_existing(self):
        # The jar file name changes with the version; the JVM key does not include it.
        base = {"Target": "jars/root/x-1.0.jar", "Type": "jar",
                "Vulnerabilities": [dict(vuln("g:x", "1.0", "CVE-9"), PkgPath="jars/root/x-1.0.jar")]}
        head = {"Target": "jars/root/x-1.1.jar", "Type": "jar",
                "Vulnerabilities": [dict(vuln("g:x", "1.1", "CVE-9"), PkgPath="jars/root/x-1.1.jar")]}
        self.run.json("sca-head.json", trivy(head))
        self.run.json("sca-base.json", trivy(base))
        os.makedirs(os.path.join(self.run.dir, "deps-head", "paths"))
        with open(os.path.join(self.run.dir, "deps-head", "paths", "root.tsv"), "w", encoding="utf-8") as f:
            f.write("g:x:1.1\tg:x:1.1 <- g:lib:2.0 <- :\n")
        _, summary = self.run.build()
        found = summary["findings"]["sca"]
        self.assertEqual([(x["status"], x["pkg"], x["id"]) for x in found], [("existing", "g:x", "CVE-9")])
        self.assertEqual(found[0]["origin"], "[root] g:x:1.1 <- g:lib:2.0 <- :")

    def test_maven_tree_origin(self):
        tree = os.path.join(self.run.dir, "deps-head", "tree")
        os.makedirs(tree)
        with open(os.path.join(tree, "tree.txt"), "w", encoding="utf-8") as f:
            f.write("fixture:fixture:jar:1.0.0\n"
                    "+- org.example:lib:jar:2.0:compile\n"
                    "|  \\- org.yaml:snakeyaml:jar:1.33:compile\n"
                    "\\- org.example:native:jar:linux:3.1:runtime\n")
        paths = report.load_maven_tree(os.path.join(self.run.dir, "deps-head"))
        self.assertEqual(paths["org.yaml:snakeyaml:1.33"], "org.yaml:snakeyaml:1.33 <- org.example:lib:2.0 <- fixture:fixture:1.0.0")
        self.assertEqual(paths["org.example:native:3.1"], "org.example:native:3.1 <- fixture:fixture:1.0.0")

    def test_base_failed_gives_unknown_for_that_part_only(self):
        self.run.statuses["sca-native-base"] = "fail"
        npm = {"Target": "package-lock.json", "Type": "npm", "Vulnerabilities": [vuln("lodash", "4.17.15", "CVE-1")]}
        self.run.json("sca-native-head.json", trivy(npm))
        self.run.source("head", "app.py", "def f(a):\n    eval(a)\n")
        self.run.source("base", "app.py", "def f(a):\n    eval(a)\n")
        self.run.json("sast-head.json", {"results": [finding("app.py", 2, "    eval(a)")], "errors": []})
        self.run.json("sast-base.json", {"results": [finding("app.py", 2, "    eval(a)")], "errors": []})
        text, summary = self.run.build()
        self.assertEqual([x["status"] for x in summary["findings"]["sca"]], ["?"])
        self.assertEqual([x["status"] for x in summary["findings"]["sast"]], ["existing"])
        self.assertIn("lock files (sca-native): comparison unavailable: base fail", text)
        self.assertIsNone(summary["sca_new"])

    def test_dependency_path_from_graph(self):
        res = {"Target": "package-lock.json", "Type": "npm",
               "Packages": [{"ID": "helper@1.0.0", "Name": "helper", "Relationship": "direct", "DependsOn": ["deep@2.0.0"]},
                            {"ID": "deep@2.0.0", "Name": "deep", "Relationship": "indirect"},
                            {"ID": "top@1.0.0", "Name": "top", "Relationship": "direct"}],
               "Vulnerabilities": [vuln("deep", "2.0.0", "CVE-5", "deep@2.0.0"), vuln("top", "1.0.0", "CVE-6", "top@1.0.0")]}
        self.run.json("sca-native-head.json", trivy(res))
        self.run.json("sca-native-base.json", trivy())
        _, summary = self.run.build()
        origin = {x["pkg"]: x["origin"] for x in summary["findings"]["sca"]}
        self.assertEqual(origin, {"deep": "deep@2.0.0 <- helper@1.0.0 (direct)", "top": "direct dependency"})

    def inventory(self, where, lockfiles):
        self.run.json(f"inv-{where}/inventory.json", {"lockfiles": lockfiles, "unpinned": [], "unsupported_locks": []})

    def test_lock_file_unread_in_head_is_not_fixed(self):
        # HEAD keeps the lock file, trivy reads nothing from it: the base CVE is unknown there, not fixed
        self.inventory("head", ["package-lock.json"])
        self.inventory("base", ["package-lock.json"])
        npm = {"Target": "package-lock.json", "Type": "npm", "Vulnerabilities": [vuln("lodash", "4.17.15", "CVE-1")]}
        self.run.json("sca-native-head.json", trivy())
        self.run.json("sca-native-base.json", trivy(npm))
        text, summary = self.run.build()
        self.assertEqual(summary["findings"]["sca_fixed"], [])
        self.assertNotIn("Fixed in the branch", text)
        self.assertIn("in HEAD: its base findings are not reported as fixed", text)
        self.assertIn("trivy recognized no packages in it; its dependencies are not checked", text)

    def test_lock_file_unread_in_base_gives_unknown(self):
        self.inventory("head", ["package-lock.json", "web/yarn.lock"])
        self.inventory("base", ["package-lock.json", "web/yarn.lock"])
        npm = {"Target": "package-lock.json", "Type": "npm", "Vulnerabilities": [vuln("lodash", "4.17.15", "CVE-1")]}
        yarn = {"Target": "web/yarn.lock", "Type": "yarn", "Vulnerabilities": [vuln("minimist", "1.2.0", "CVE-2")]}
        self.run.json("sca-native-head.json", trivy(npm, yarn))
        self.run.json("sca-native-base.json", trivy(npm))
        text, summary = self.run.build()
        got = sorted((x["status"], x["target"]) for x in summary["findings"]["sca"])
        self.assertEqual(got, [("?", "web/yarn.lock"), ("existing", "package-lock.json")])
        self.assertIsNone(summary["sca_new"])
        self.assertIn("`web/yarn.lock`: trivy recognized no packages in it in the base: its findings are `?`", text)

    def test_new_lock_file_is_new(self):
        # a lock file the base does not have is not "unread" in the base: its findings are new
        self.inventory("head", ["package-lock.json"])
        self.inventory("base", [])
        npm = {"Target": "package-lock.json", "Type": "npm", "Vulnerabilities": [vuln("lodash", "4.17.15", "CVE-1")]}
        self.run.json("sca-native-head.json", trivy(npm))
        self.run.json("sca-native-base.json", trivy())
        _, summary = self.run.build()
        self.assertEqual([x["status"] for x in summary["findings"]["sca"]], ["new"])
        self.assertEqual(summary["sca_new"], 1)

    def test_file_dependency_origin(self):
        head = {"Target": "jars/root/files/commons-text-1.9.jar", "Type": "jar",
                "Vulnerabilities": [dict(vuln("org.apache.commons:commons-text", "1.9", "CVE-2022-42889"),
                                         PkgPath="jars/root/files/commons-text-1.9.jar")]}
        self.run.json("sca-head.json", trivy(head))
        self.run.json("sca-base.json", trivy())
        os.makedirs(os.path.join(self.run.dir, "deps-head", "files"))
        with open(os.path.join(self.run.dir, "deps-head", "files", "root.tsv"), "w", encoding="utf-8") as f:
            f.write("commons-text-1.9.jar\tlibs/commons-text-1.9.jar\n")
        _, summary = self.run.build()
        self.assertEqual(summary["findings"]["sca"][0]["origin"], "[root] file dependency libs/commons-text-1.9.jar")

    def test_no_graph_is_unknown(self):
        res = {"Target": "requirements.txt", "Type": "pip", "Packages": [{"ID": "a@1", "Name": "a"}],
               "Vulnerabilities": [vuln("a", "1", "CVE-7", "a@1")]}
        self.run.json("sca-native-head.json", trivy(res))
        self.run.json("sca-native-base.json", trivy())
        _, summary = self.run.build()
        self.assertTrue(summary["findings"]["sca"][0]["origin"].startswith("direct/transitive: unknown"))


def jar_result(pkg, ver, vid, fixed="9.9.9", path="jars/root/x.jar"):
    v = dict(vuln(pkg, ver, vid), PkgPath=path, FixedVersion=fixed)
    return {"Target": path, "Type": "jar", "Vulnerabilities": [v]}


class ActionsTest(unittest.TestCase):
    def setUp(self):
        self.run = Run()

    def tearDown(self):
        self.run.close()

    def gradle_paths(self, *lines):
        os.makedirs(os.path.join(self.run.dir, "deps-head", "paths"), exist_ok=True)
        with open(os.path.join(self.run.dir, "deps-head", "paths", "root.tsv"), "w", encoding="utf-8") as f:
            f.write("".join(line + "\n" for line in lines))

    def actions(self):
        text, summary = self.run.build()
        return text, {a["direct"]: a for a in summary["findings"]["actions"]}

    def test_gradle_direct_and_transitive(self):
        self.run.json("sca-head.json", trivy(jar_result("org.yaml:snakeyaml", "1.33", "CVE-2022-1471", "2.0"),
                                             jar_result("g:deep", "1.0", "CVE-8", "1.2", "jars/root/deep.jar")))
        self.run.json("sca-base.json", trivy())
        self.gradle_paths("org.yaml:snakeyaml:1.33\torg.yaml:snakeyaml:1.33 <- :", "g:deep:1.0\tg:deep:1.0 <- g:lib:2.0 <- :")
        text, acts = self.actions()
        self.assertEqual(acts["org.yaml:snakeyaml:1.33"]["action"], "upgrade org.yaml:snakeyaml to >= 2.0")
        self.assertEqual(acts["org.yaml:snakeyaml:1.33"]["kind"], "direct")
        self.assertEqual(acts["g:lib:2.0"]["action"], "upgrade g:lib:2.0 to a version that brings g:deep >= 1.2, or pin g:deep")
        self.assertIn("### What to change in the build", text)
        self.assertIn("first path found", text)
        # no version of the parent is invented: the only version in the action is the child's fixed version
        self.assertNotRegex(acts["g:lib:2.0"]["action"], r"g:lib:2\.0 to >=")

    def test_maven_tree_direct(self):
        self.run.json("sca-head.json", trivy(jar_result("org.yaml:snakeyaml", "1.33", "CVE-2022-1471", "2.0")))
        self.run.json("sca-base.json", trivy())
        tree = os.path.join(self.run.dir, "deps-head", "tree")
        os.makedirs(tree)
        with open(os.path.join(tree, "tree.txt"), "w", encoding="utf-8") as f:
            f.write("fixture:fixture:jar:1.0.0\n+- org.example:lib:jar:2.0:compile\n|  \\- org.yaml:snakeyaml:jar:1.33:compile\n")
        _, acts = self.actions()
        self.assertEqual(list(acts), ["org.example:lib:2.0"])
        self.assertEqual(acts["org.example:lib:2.0"]["kind"], "transitive")

    def test_lock_file_graph_and_unknown(self):
        graph = {"Target": "package-lock.json", "Type": "npm",
                 "Packages": [{"ID": "helper@1.0.0", "Name": "helper", "Relationship": "direct", "DependsOn": ["node-fetch@2.6.0"]},
                              {"ID": "node-fetch@2.6.0", "Name": "node-fetch", "Relationship": "indirect"},
                              {"ID": "lodash@4.17.15", "Name": "lodash", "Relationship": "direct"}],
                 "Vulnerabilities": [dict(vuln("node-fetch", "2.6.0", "CVE-2022-0235", "node-fetch@2.6.0"), FixedVersion="2.6.7"),
                                     dict(vuln("node-fetch", "2.6.0", "CVE-2020-15168", "node-fetch@2.6.0"), FixedVersion="2.6.1"),
                                     dict(vuln("lodash", "4.17.15", "CVE-2021-23337", "lodash@4.17.15"), FixedVersion="4.17.21")]}
        flat = {"Target": "requirements.txt", "Type": "pip", "Packages": [{"ID": "a@1", "Name": "a"}],
                "Vulnerabilities": [dict(vuln("a", "1", "CVE-7", "a@1"), FixedVersion="")]}
        self.run.json("sca-native-head.json", trivy(graph, flat))
        self.run.json("sca-native-base.json", trivy())
        _, acts = self.actions()
        # the highest fixed version over the package's CVEs
        self.assertEqual(acts["helper@1.0.0"]["action"],
                         "upgrade helper@1.0.0 to a version that brings node-fetch >= 2.6.7, or pin node-fetch")
        self.assertEqual(acts["lodash@4.17.15"]["action"], "upgrade lodash to >= 4.17.21")
        self.assertEqual(acts["origin unknown"]["action"], "a: no fixed version yet")
        self.assertEqual(acts["origin unknown"]["where"], ["requirements.txt"])

    def test_branching_fixed_versions_are_listed(self):
        res = {"Target": "go.mod", "Type": "gomod", "Packages": [{"ID": "x@1", "Name": "x", "Relationship": "direct"}],
               "Vulnerabilities": [dict(vuln("x", "1", "CVE-1", "x@1"), FixedVersion="1.5.2, 2.1.0"),
                                   dict(vuln("x", "1", "CVE-2", "x@1"), FixedVersion="1.5.0")]}
        self.run.json("sca-native-head.json", trivy(res))
        self.run.json("sca-native-base.json", trivy())
        _, acts = self.actions()
        # per CVE the lowest fix on the installed release line (1.5.2, not 2.1.0), then the highest over CVEs
        self.assertEqual(acts["x@1"]["action"], "upgrade x to >= 1.5.2")

    def test_some_cves_without_fix_are_named(self):
        res = {"Target": "go.mod", "Type": "gomod", "Packages": [{"ID": "x@1.0", "Name": "x", "Relationship": "direct"}],
               "Vulnerabilities": [dict(vuln("x", "1.0", "CVE-1", "x@1.0"), FixedVersion=">=1.2"),
                                   dict(vuln("x", "1.0", "CVE-2", "x@1.0"), FixedVersion="")]}
        self.run.json("sca-native-head.json", trivy(res))
        self.run.json("sca-native-base.json", trivy())
        _, acts = self.actions()
        self.assertEqual(acts["x@1.0"]["action"], "upgrade x to >= 1.2 (1 of its CVEs have no fixed version yet)")

    def test_file_dependency(self):
        self.run.json("sca-head.json", trivy(jar_result("org.apache.commons:commons-text", "1.9", "CVE-2022-42889", "1.10.0",
                                                        "jars/root/files/commons-text-1.9.jar")))
        self.run.json("sca-base.json", trivy())
        os.makedirs(os.path.join(self.run.dir, "deps-head", "files"))
        with open(os.path.join(self.run.dir, "deps-head", "files", "root.tsv"), "w", encoding="utf-8") as f:
            f.write("commons-text-1.9.jar\tlibs/commons-text-1.9.jar\n")
        _, acts = self.actions()
        self.assertEqual(acts["libs/commons-text-1.9.jar"]["action"],
                         "replace the file with org.apache.commons:commons-text >= 1.10.0")

    def test_existing_are_listed_after_new(self):
        old = {"Target": "go.mod", "Type": "gomod", "Packages": [{"ID": "a@1", "Name": "a", "Relationship": "direct"},
                                                                 {"ID": "b@1", "Name": "b", "Relationship": "direct"}],
               "Vulnerabilities": [dict(vuln("a", "1", "CVE-1", "a@1"), Severity="CRITICAL")]}
        new = json.loads(json.dumps(old))
        new["Vulnerabilities"].append(dict(vuln("b", "1", "CVE-2", "b@1"), Severity="LOW"))
        self.run.json("sca-native-head.json", trivy(new))
        self.run.json("sca-native-base.json", trivy(old))
        _, summary = self.run.build()
        got = [(a["direct"], a["new"]) for a in summary["findings"]["actions"]]
        self.assertEqual(got, [("b@1", 1), ("a@1", 0)])


class PartsTest(unittest.TestCase):
    def setUp(self):
        self.run = Run()

    def tearDown(self):
        self.run.close()

    def test_not_requested_part_is_not_empty(self):
        for name in ("sca", "sca-base", "sca-native", "sca-native-base"):
            self.run.statuses[name] = "skip"
        text, summary = self.build_with(parts="sast", skip_comment="not requested (--parts sast)")
        self.assertIn("- Parts: requested sast; **not requested: sca, image**", text)
        self.assertIn("## SCA: not requested (--parts sast)", text)
        self.assertNotIn("## SCA: 0", text)
        self.assertIsNone(summary["sca_total"])
        self.assertEqual(summary["parts"], "sast")

    def test_sast_not_requested(self):
        for name in ("sast", "sast-base"):
            self.run.statuses[name] = "skip"
        text, summary = self.build_with(parts="sca", skip_comment="not requested (--parts sca)")
        self.assertIn("## SAST: not requested (--parts sca)", text)
        self.assertIsNone(summary["sast_total"])
        self.assertIsNone(summary["sast_new"])

    def build_with(self, parts, skip_comment):
        text_status = os.path.join(self.run.dir, "status.tsv")

        def build():
            report._source_cache.clear()
            with open(os.path.join(self.run.dir, "meta.json"), "w", encoding="utf-8") as f:
                json.dump({"REPO": self.run.repo, "NAME": "fixture", "BRANCH": "feature", "HEAD_SHA": "1234567890ab",
                           "DIRTY": "0", "BASE_REF": "main", "BASE_SHA": "abcdef123456", "LANGS": "python",
                           "BUILD": "none", "RULES": "registry", "PARTS": parts}, f)
            with open(text_status, "w", encoding="utf-8") as f:
                for name, state in self.run.statuses.items():
                    f.write(f"{name}\t{state}\t{skip_comment if state == 'skip' else name + ' ok'}\n")
            return report.build(self.run.dir)
        return build()


class ImageTest(unittest.TestCase):
    def setUp(self):
        self.run = Run()

    def tearDown(self):
        self.run.close()

    def image(self, label, state, data):
        self.run.statuses[f"docker-{label}"] = state
        path = os.path.join(self.run.dir, f"docker-{label}.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write(data if isinstance(data, str) else json.dumps(data))

    def test_failed_scan_output_is_not_a_clean_image(self):
        self.image("broken", "fail", "")
        text, summary = self.run.build()
        self.assertIn("## Image `broken`: not checked (fail: docker-broken fail reason)", text)
        self.assertNotIn("## Image broken", text)
        self.assertNotIn("Full snapshot", text)
        self.assertIsNone(summary["images_total"])

    def test_ok_image_is_counted_and_failed_one_is_not(self):
        alpine = {"ArtifactName": "alpine:3.20.0", "Results": [
            {"Target": "alpine", "Class": "os-pkgs", "Vulnerabilities": [vuln("busybox", "1.36", "CVE-3")]}]}
        self.image("alpine", "ok", alpine)
        self.image("broken", "fail", '{"Results": [')
        text, summary = self.run.build()
        self.assertIn("## Image alpine:3.20.0: 1 vulnerabilit(ies)", text)
        self.assertEqual(summary["images_total"], 1)


class FunctionTest(unittest.TestCase):
    def check(self, name, text, expected):
        d = tempfile.mkdtemp()
        try:
            path = os.path.join(d, name)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            report._source_cache.clear()
            got = {line: report.enclosing_function(path, line) for line in expected}
            self.assertEqual(got, expected)
        finally:
            shutil.rmtree(d)

    def test_python(self):
        self.check("a.py", "def f(x):\n    eval(x)\nclass C:\n    async def m(self, y):\n        if y:\n"
                           "            eval(y)\n    Z = eval('1')\nW = eval('2')\n", {2: "f", 6: "m", 7: "", 8: ""})

    def test_javascript(self):
        self.check("a.js", "function h(req) {\n  eval(req)\n}\nconst k = (a, b = 1) => {\n  eval(a)\n}\n"
                           "class S {\n  handle(req) {\n    eval(req)\n  }\n}\n", {2: "h", 5: "k", 9: "handle"})

    def test_brace_scope(self):
        # a module-level line after a closed function is outside any function; a line after an inner block is inside
        self.check("m.js", "function old(a) {\n  return a\n}\neval(input)\nfunction f(a) {\n  if (a) {\n    x('}')\n  }\n"
                           "  eval(a)\n}\nconst g = (b) => eval(b)\n", {4: "", 9: "f", 11: "g"})
        self.check("m.go", "package m\n\nfunc a() {\n}\n\nvar x = exec.Command(\"ls\")\n", {6: ""})
        self.check("B.java", "class B {\n  void m() {\n  }\n  String s = run(\"x\");\n}\n", {4: ""})

    def test_typescript(self):
        self.check("a.ts", "export async function g(r: string): Promise<void> {\n  eval(r)\n}\n"
                           "export const t = async (q: string): Promise<void> => {\n  eval(q)\n}\n", {2: "g", 5: "t"})

    def test_java_go_rust(self):
        self.check("A.java", "class A {\n  public String get(String a) {\n    String q = a;\n    return q;\n  }\n}\n", {3: "get"})
        self.check("m.go", "package m\n\nfunc (s *S) Run(c string) {\n\t_ = c\n}\n", {4: "Run"})
        self.check("m.rs", "pub fn run(c: &str) {\n    let _ = c;\n}\n", {2: "run"})


if __name__ == "__main__":
    unittest.main()
