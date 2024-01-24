# ec-toys

环境要求:
```
python >= 3.6.0
```

## 编译

安装依赖包
```
dnf install -y python3-devel libvirt-python3 python3-libs
dnf install -y libvirt-devel gcc libffi-devel python3-cryptography python3-netaddr python3-debtcollector python3-pyyaml
python3 -m pip install pip -U

pip3 install python-novaclient python-glanceclient python-neutronclient \
    python-glanceclient python-keystoneclient python-cinderclient
```
下载依赖包
```
python3 -m pip wheel --prefer-binary --wheel-dir=dist ./
```

## 运行

1. 源码

    ```
    export PYTHONPATH=./
    python3 ectoys/cmd/test.py
   ```

