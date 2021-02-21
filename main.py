#!/usr/bin/env python3

import json
from dataclasses import dataclass
from logging import Logger
from pathlib import Path
from typing import Any, Optional, List, Dict

import boto3
import requests

logger: Logger = Logger(__name__)

BASE_CONFIG_PATH: Path = Path('./.config')

AWS_CONFIG_FILENAME: str = 'aws_config.json'
HOSTED_ZONE_CONFIG_FILENAME: str = 'hosted_zone_config.json'


def _validate_ip_v4(raw_ip_v4: str) -> str:
	raw_bytes: List[str] = raw_ip_v4.strip().split('.')

	if len(raw_bytes) != 4:
		raise ValueError(f"Number of bytes ({len(raw_bytes)}) does not match expected length for {raw_ip_v4}")

	parsed_bytes: List[int] = []

	for raw_byte in raw_bytes:
		parsed_byte: int
		try:
			parsed_byte = int(raw_byte)
		except ValueError as e:
			raise ValueError(f"Invalid type {raw_byte} for {raw_ip_v4}: {e!r}")

		if not (0 <= parsed_byte <= 255):
			raise ValueError(f"Byte {parsed_byte} out of range for {raw_ip_v4}")

		parsed_bytes.append(parsed_byte)

	return '.'.join(map(str, parsed_bytes))


def get_public_ip_v4() -> str:
	response: requests.Response = requests.get('https://api.ipify.org')
	response.raise_for_status()

	raw_ip: str = response.text
	validated_ip_v4: str = _validate_ip_v4(raw_ip)

	return validated_ip_v4


def get_boto3_session() -> boto3.Session:
	loaded_json: Dict[str, str]
	with open(BASE_CONFIG_PATH / AWS_CONFIG_FILENAME, encoding='utf-8') as f:
		loaded_json = json.load(f)

	return boto3.Session(**loaded_json)


def update_route_53_record_set(
		router_53_client,
		hosted_zone_id: str,

		record_set_name: str, record_set_type: str, record_ttl: int,
		record_set_value: str
) -> None:
	router_53_client.change_resource_record_sets(
		HostedZoneId=hosted_zone_id,
		ChangeBatch=dict(
			Changes=[dict(
				Action='UPSERT',  # Update or insert,
				ResourceRecordSet=dict(
					Name=record_set_name,
					Type=record_set_type,
					TTL=record_ttl,
					ResourceRecords=[dict(Value=record_set_value)]
				),
			)]
		)
	)


@dataclass
class RecordInfo:
	target_hosted_zone_name: str
	target_record_set_name: str
	target_record_set_type: str = 'A'
	target_record_set_ttl: int = 300


def load_record_info() -> RecordInfo:
	with open(BASE_CONFIG_PATH / HOSTED_ZONE_CONFIG_FILENAME, encoding='utf-8') as f:
		parsed_record_info: Dict[str, Any] = json.load(f)
		return RecordInfo(**parsed_record_info)


if __name__ == '__main__':
	try:
		record_info: RecordInfo = load_record_info()

		public_ip: str = get_public_ip_v4()

		session: boto3.Session = get_boto3_session()
		route_53_client = session.client('route53')

		hosted_zones: List[Dict[str, Any]] = route_53_client.list_hosted_zones_by_name()['HostedZones']
		target_hosted_zone: Dict[str, Any] = next(
			filter(lambda hz: hz['Name'] == record_info.target_hosted_zone_name, hosted_zones))

		target_hosted_zone_records: List[Dict[str, Any]] = route_53_client.list_resource_record_sets(
			HostedZoneId=target_hosted_zone['Id']
		)['ResourceRecordSets']

		target_record: Optional[Dict[str, Any]] = next(
			filter(lambda r: r['Name'] == record_info.target_record_set_name, target_hosted_zone_records), None
		)

		update_route_53_record_set(
			route_53_client,
			target_hosted_zone['Id'],

			record_set_name=record_info.target_record_set_name,
			record_set_type=record_info.target_record_set_type,
			record_ttl=record_info.target_record_set_ttl,

			record_set_value=public_ip,
		)

	except Exception as e:
		logger.critical(f"Unhandled exception: {e!r}", exc_info=True)
