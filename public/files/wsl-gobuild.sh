#!/bin/bash
# usage: wsl-gobuild.sh <label>
# 5 runs of `go build -a -o /dev/null cmd/go` with an empty build cache, inside WSL.
# Assumes Go is unpacked in ~/go and this script sits next to a results/ directory.
label=$1
export GOROOT="$HOME/go" GOPATH="$HOME/gopath" GOFLAGS=-p=8 GOCACHE="$HOME/gocache-bench" GOTOOLCHAIN=local
export PATH="$HOME/go/bin:$PATH"
mkdir -p results; out=results/gobuild-$label.txt
echo "# kernel: $(uname -r) $(go version)" > $out
for i in 1 2 3 4 5; do
  rm -rf $GOCACHE
  /usr/bin/time -f "real %e user %U sys %S" go build -a -o /dev/null cmd/go 2>> $out
done
cat $out
