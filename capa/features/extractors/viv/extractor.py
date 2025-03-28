# Copyright 2021 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
from typing import Any, Iterator
from pathlib import Path

import viv_utils
import viv_utils.flirt

import capa.features.extractors.common
import capa.features.extractors.viv.file
import capa.features.extractors.viv.insn
import capa.features.extractors.viv.global_
import capa.features.extractors.viv.function
import capa.features.extractors.viv.basicblock
from capa.features.common import Feature
from capa.features.address import Address, AbsoluteVirtualAddress
from capa.features.extractors.strings import DEFAULT_STRING_LENGTH
from capa.features.extractors.base_extractor import (
    BBHandle,
    InsnHandle,
    SampleHashes,
    FunctionHandle,
    StaticFeatureExtractor,
)

logger = logging.getLogger(__name__)


class VivisectFeatureExtractor(StaticFeatureExtractor):
    def __init__(self, vw, path: Path, os, min_str_len: int = DEFAULT_STRING_LENGTH):
        self.vw = vw
        self.path = path
        self.buf = path.read_bytes()
        self.min_str_len = min_str_len
        super().__init__(hashes=SampleHashes.from_bytes(self.buf))

        # pre-compute these because we'll yield them at *every* scope.
        self.global_features: list[tuple[Feature, Address]] = []
        self.global_features.extend(capa.features.extractors.viv.file.extract_file_format(ctx={"buf": self.buf}))
        self.global_features.extend(capa.features.extractors.common.extract_os(self.buf, os))
        self.global_features.extend(capa.features.extractors.viv.global_.extract_arch(self.vw))

    def get_base_address(self):
        # assume there is only one file loaded into the vw
        return AbsoluteVirtualAddress(list(self.vw.filemeta.values())[0]["imagebase"])

    def extract_global_features(self):
        yield from self.global_features

    def extract_file_features(self):
        yield from capa.features.extractors.viv.file.extract_features(
            ctx={"vw": self.vw, "buf": self.buf, "min_str_len": self.min_str_len}
        )

    def get_functions(self) -> Iterator[FunctionHandle]:
        cache: dict[str, Any] = {}
        for va in sorted(self.vw.getFunctions()):
            yield FunctionHandle(
                address=AbsoluteVirtualAddress(va),
                inner=viv_utils.Function(self.vw, va),
                ctx={"cache": cache, "min_str_len": self.min_str_len},
            )

    def extract_function_features(self, fh: FunctionHandle) -> Iterator[tuple[Feature, Address]]:
        yield from capa.features.extractors.viv.function.extract_features(fh)

    def get_basic_blocks(self, fh: FunctionHandle) -> Iterator[BBHandle]:
        f: viv_utils.Function = fh.inner
        for bb in f.basic_blocks:
            yield BBHandle(address=AbsoluteVirtualAddress(bb.va), inner=bb)

    def extract_basic_block_features(self, fh: FunctionHandle, bbh) -> Iterator[tuple[Feature, Address]]:
        yield from capa.features.extractors.viv.basicblock.extract_features(fh, bbh)

    def get_instructions(self, fh: FunctionHandle, bbh: BBHandle) -> Iterator[InsnHandle]:
        bb: viv_utils.BasicBlock = bbh.inner
        for insn in bb.instructions:
            yield InsnHandle(address=AbsoluteVirtualAddress(insn.va), inner=insn)

    def extract_insn_features(
        self, fh: FunctionHandle, bbh: BBHandle, ih: InsnHandle
    ) -> Iterator[tuple[Feature, Address]]:
        yield from capa.features.extractors.viv.insn.extract_features(fh, bbh, ih)

    def is_library_function(self, addr):
        return viv_utils.flirt.is_library_function(self.vw, addr)

    def get_function_name(self, addr):
        return viv_utils.get_function_name(self.vw, addr)
