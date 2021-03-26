COMMIT=${1}
export COMMIT
TAG="${2}/afqsi:${COMMIT}"
TAG="$(echo "${TAG}" | tr -d '[:space:]')"
echo $TAG
docker build --no-cache -t $TAG .
docker push $TAG