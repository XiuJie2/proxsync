#!/usr/bin/env python3
"""
测试网络接口同步和增量哈希功能
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from state_db import compute_config_hash

def test_compute_config_hash():
    """测试配置哈希包含网络接口"""
    
    # 基础 VM 配置
    vm_config = {
        'memory': 4096,
        'vcpus': 4,
        'ostype': 'l26',
        'description': 'Test VM',
        'tags': []
    }
    tags = ['prod', 'web']
    
    # 计算无网络接口的哈希
    hash1 = compute_config_hash(vm_config, tags, None)
    print(f"Hash without networks: {hash1}")
    
    # 添加网络接口
    networks = [
        {'name': 'net0', 'mac_address': 'aa:bb:cc:dd:ee:ff', 'bridge': 'vmbr0', 'gateway': ''},
        {'name': 'net1', 'mac_address': '11:22:33:44:55:66', 'bridge': '', 'gateway': '192.168.1.1'}
    ]
    
    # 计算有网络接口的哈希
    hash2 = compute_config_hash(vm_config, tags, networks)
    print(f"Hash with networks:   {hash2}")
    
    # 验证哈希不同
    assert hash1 != hash2, "Hash should differ when networks change"
    print("✓ Network interfaces affect hash")
    
    # 修改接口后哈希变化
    networks_modified = [
        {'name': 'net0', 'mac_address': 'aa:bb:cc:dd:ee:ff', 'bridge': 'vmbr1', 'gateway': ''},  # bridge changed
        {'name': 'net1', 'mac_address': '11:22:33:44:55:66', 'bridge': '', 'gateway': '192.168.1.1'}
    ]
    hash3 = compute_config_hash(vm_config, tags, networks_modified)
    assert hash2 != hash3, "Hash should differ when bridge changes"
    print("✓ Bridge change detected")
    
    # 空网络列表与None区别
    hash_empty = compute_config_hash(vm_config, tags, [])
    assert hash1 == hash_empty, "Empty list should equal None"
    print("✓ Empty networks equals None")
    
    print("\n✅ All hash tests passed!")

def test_parse_network_config():
    """测试网络配置解析"""
    from sync import OptimizedPVEToNetBoxSync
    
    # 创建一个实例（仅测试方法）
    sync = OptimizedPVEToNetBoxSync.__new__(OptimizedPVEToNetBoxSync)
    
    # 测试解析
    config_str = "virtio=aa:bb:cc:dd:ee:ff,bridge=vmbr0,mtu=1500"
    result = sync.parse_network_config(config_str)
    
    expected = {
        'virtio': 'aa:bb:cc:dd:ee:ff',
        'bridge': 'vmbr0',
        'mtu': '1500'
    }
    assert result == expected, f"Parse failed: {result} != {expected}"
    print("✓ parse_network_config works")

if __name__ == '__main__':
    print("=== Testing Network Interface Sync ===\n")
    
    try:
        test_compute_config_hash()
        print()
        test_parse_network_config()
        print("\n✅ All tests passed!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
