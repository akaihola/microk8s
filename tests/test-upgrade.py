import os
import time
from validators import (
    validate_dns_dashboard,
    validate_storage,
    validate_ingress,
    validate_gpu,
    validate_registry,
    validate_forward,
    validate_metrics_server
)
from subprocess import check_call, CalledProcessError, check_output
from utils import microk8s_enable, wait_for_pod_state, microk8s_disable, wait_for_installation

upgrade_from = os.environ.get('UPGRADE_MICROK8S_FROM', 'beta')
# Have UPGRADE_MICROK8S_TO point to a file to upgrade to that file
upgrade_to = os.environ.get('UPGRADE_MICROK8S_TO', 'edge')


class TestUpgrade(object):
    """
    Validates a microk8s upgrade path
    """

    def test_upgrade(self):
        """
        Deploy, probe, upgrade, validate nothing broke.

        """
        print("Testing upgrade from {} to {}".format(upgrade_from, upgrade_to))

        cmd = "sudo snap install microk8s --classic --channel={}".format(upgrade_from).split()
        check_call(cmd)
        wait_for_installation()
        if is_container():
            # In some setups (eg LXC on GCE) the hashsize nf_conntrack file under
            # sys is marked as rw but any update on it is failing causing kube-proxy
            # to fail.
            here = os.path.dirname(os.path.abspath(__file__))
            apply_patch = os.path.join(here, "patch-kube-proxy.sh")
            check_call("sudo {}".format(apply_patch).split())

        # Run through the validators and
        # select those that were valid for the original snap
        test_matrix = {}
        try:
            enable = microk8s_enable("dns")
            wait_for_pod_state("", "kube-system", "running", label="k8s-app=kube-dns")
            assert "Nothing to do for" not in enable
            enable = microk8s_enable("dashboard")
            assert "Nothing to do for" not in enable
            validate_dns_dashboard()
            test_matrix['dns_dashboard'] = validate_dns_dashboard
        except:
            print('Will not test dns-dashboard')

        try:
            enable = microk8s_enable("storage")
            assert "Nothing to do for" not in enable
            validate_storage()
            test_matrix['storage'] = validate_storage
        except:
            print('Will not test storage')

        try:
            enable = microk8s_enable("ingress")
            assert "Nothing to do for" not in enable
            validate_ingress()
            test_matrix['ingress'] = validate_ingress
        except:
            print('Will not test ingress')

        try:
            enable = microk8s_enable("gpu")
            assert "Nothing to do for" not in enable
            validate_gpu()
            test_matrix['gpu'] = validate_gpu
        except:
            print('Will not test gpu')

        try:
            enable = microk8s_enable("registry")
            assert "Nothing to do for" not in enable
            validate_registry()
            test_matrix['registry'] = validate_registry
        except:
            print('Will not test registry')

        try:
            validate_forward()
            test_matrix['forward'] = validate_forward
        except:
            print('Will not test port forward')

        try:
            enable = microk8s_enable("metrics-server")
            assert "Nothing to do for" not in enable
            validate_metrics_server()
            test_matrix['metrics_server'] = validate_metrics_server
        except:
            print('Will not test the metrics server')

        # Refresh the snap to the target
        if upgrade_to.endswith('.snap'):
            cmd = "sudo snap install {} --classic --dangerous".format(upgrade_to).split()
        else:
            cmd = "sudo snap refresh microk8s --channel={}".format(upgrade_to).split()
        check_call(cmd)
        # Allow for the refresh to be processed
        time.sleep(10)
        wait_for_installation()

        # Test any validations that were valid for the original snap
        for test, validation in test_matrix.items():
            print("Testing {}".format(test))
            validation()

        if not is_container():
            # On lxc umount docker overlay is not permitted.
            check_call("sudo snap remove microk8s".split())


def is_container():
    '''
    Returns: True if the deployment is in a VM/container.

    '''
    try:
        if os.path.isdir('/run/systemd/system'):
            container = check_output('sudo systemd-detect-virt --container'.split())
            print("Tests are running in {}".format(container))
            return True
    except CalledProcessError:
        print("systemd-detect-virt did not detect a container")

    if os.path.exists('/run/container_type'):
        return True

    try:
        check_call("sudo grep -E (lxc|hypervisor) /proc/1/environ /proc/cpuinfo".split())
        print("Tests are running in an undetectable container")
        return True
    except CalledProcessError:
        print("no indication of a container in /proc")

    return False
