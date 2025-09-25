# Copyright 2025 ApeCloud, Inc.
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

import os

from aperag.source.utils import FeishuBlockParser, FeishuClient

ctx = {
    "app_id": os.environ.get("APP_ID"),
    "app_secret": os.environ.get("APP_SECRET"),
}

node_id = "GnDvdxaSRoBllOxyucWcrEuincg"

client = FeishuClient(ctx)
blocks = client.get_docx_blocks(node_id)
content = FeishuBlockParser(node_id, blocks).gen()
print(content)
