# ec-toys

环境要求:
```
python >= 3.6.0
```

## 编译

安装依赖包
```
dnf install -y python3-devel libvirt-python3 libvirt-devel
python3 -m pip install pip -U
pip3 install python-openstackclient python-novaclient python-cinderclient python-neutron-client

```

```
python3 -m pip wheel --prefer-binary --no-deps --wheel-dir=dist ./
```
