#!/bin/bash
TAG="metube"
PUSH="false"

# Proccess Arguments

while getopts ":hhelpf:t:p:" ARGS;
do
    case $ARGS in
        h|help )
            echo -e "Usgae:\n\t-t \"Tag\"\n\t\tuse a specific Tag\n\t-p true\n\t\tPush the Image do a registry. Needs to be logged in (docker login).\n\t-h\n\t\t Show this Help Dialog"
            exit 1
            ;;
        t )
            TAG="${OPTARG}"
            ;;
        p )
            PUSH="${OPTARG}"
            ;;
    esac
done

# Fail on Error
set -e

# Register Arm executables to run on x64 machines
docker run --rm --privileged docker/binfmt:820fdd95a9972a5308930a2bdfb8573dd4447ad3

# Test if qemu is enabeld
cat /proc/sys/fs/binfmt_misc/qemu-aarch64 | head -n 1 | grep -q "enabled"

# Create a Builder if needed
if docker buildx ls | grep -q "multiArchBuilder"; then
    echo "Builder \"multiArchBuilder\" aready exists."
else
    echo "Builder \"multiArchBuilder\" will be created."

    docker buildx create --name "multiArchBuilder"
fi

# Switch to Builder "multiArchBuilder"
docker buildx use "multiArchBuilder"

# Test if current Builder Contains needed Architectures
BOOTSTRAP=$(docker buildx inspect --bootstrap)

echo $BOOTSTRAP | grep -q "linux/amd64"
echo $BOOTSTRAP | grep -q "linux/arm64"
echo $BOOTSTRAP | grep -q "linux/arm/v7"

# Build Image
echo "Use Tag \"$TAG\" for Build"
if [ "$PUSH" = "true" ]; then
    # Build with Push
    docker buildx build --platform linux/arm,linux/arm64,linux/amd64 -t "$TAG" --push .
else
    # Build without Push
    docker buildx build --platform linux/arm,linux/arm64,linux/amd64 -t "$TAG" .
fi
