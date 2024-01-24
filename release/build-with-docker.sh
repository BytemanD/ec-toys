
which podman > /dev/null
if [[ $? -eq 0 ]]; then
    BUILD_CMD=podman
else
    BUILD_CMD=docker
fi
PROJECT_PATH=$(pwd)

echo "INFO" "Build with ${BUILD_CMD}"

cd release
${BUILD_CMD} build \
    -v ${PROJECT_PATH}:/root/ec-toys \
    -v /etc/localtime:/etc/localtime \
    --build-arg DATE="$(date +'%F %T')" \
    --file Dockerfile \
    ./
