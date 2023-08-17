import boto3

from botocore.exceptions import ClientError
from io import BytesIO

BODY = 'Body'
BUCKET_ROOT = ''
CONTENTS = 'Contents'
DOT = '.'
KEY = 'Key'
LINE_BREAK = '\n'
OBJECTS_SEPARATOR = '/'

SUCCESS_NO_EXTENSION = '_SUCCESS'
SUCCESS_WITH_CRC_EXTENSION = f'.{SUCCESS_NO_EXTENSION}.crc'


class S3ObjectsMerger:

    def __init__(self):
        self.__client = None
        self.__bucket_name = None
        self.__new_object_key = None
        self.__objects_to_merge_initial_name = None
        self.__objects_to_merge_prefix = None

    def merge(self,
              bucket_name: str,
              new_object_key: str,
              objects_to_merge_initial_name: str,
              objects_to_merge_prefix=BUCKET_ROOT,
              is_success_files_deletion_enabled=True):

        self.__client = boto3.client('s3')
        self.__objects_to_merge_initial_name = objects_to_merge_initial_name
        self.__bucket_name = self.__validate_bucket(bucket_name)
        self.__new_object_key = self.__validate_object_key(new_object_key)

        self.__add_separator_to_prefix_if_absent(objects_to_merge_prefix)
        objects_to_merge = self.__validate_objects_to_merge_prefix()

        new_object_extension = self.__extract_object_extension_from_key()
        new_object = self.__merge_objects(objects_to_merge, new_object_extension)

        new_object_without_last_blank_line = new_object[:-1]
        self.__upload_object_to_bucket(new_object_without_last_blank_line)

        if is_success_files_deletion_enabled:
            self.__delete_success_objects()

        self.__client.close()

    def __validate_bucket(self, bucket_name: str):
        self.__check_if_bucket_name_is_informed(bucket_name)
        self.__check_if_bucket_exists(bucket_name)

        return bucket_name

    @staticmethod
    def __check_if_bucket_name_is_informed(bucket_name):
        if not bucket_name:
            raise ValueError('Bucket not informed!')

    @staticmethod
    def __check_if_bucket_exists(bucket_name: str):
        try:
            boto3.resource('s3').meta.client.head_bucket(Bucket=bucket_name)
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                raise BucketNotFoundException()

    @staticmethod
    def __validate_object_key(new_object_key: str):
        if not new_object_key:
            raise ValueError('Object key not informed!')

        return new_object_key

    def __add_separator_to_prefix_if_absent(self, objects_to_merge_prefix: str):
        self.__objects_to_merge_prefix = f'{objects_to_merge_prefix}{OBJECTS_SEPARATOR}' \
            if objects_to_merge_prefix and not objects_to_merge_prefix.endswith(OBJECTS_SEPARATOR) \
            else objects_to_merge_prefix

    def __validate_objects_to_merge_prefix(self):
        objects = self.__client.list_objects_v2(Bucket=self.__bucket_name, Prefix=self.__objects_to_merge_prefix)
        if CONTENTS not in objects:
            raise ObjectNotFoundException('Prefix not found!')
        return objects

    def __extract_object_extension_from_key(self) -> str:
        return self.__new_object_key.split(DOT)[-1]

    def __merge_objects(self, objects_to_merge, new_object_extension):
        new_object = ''
        total_objects_to_merge_with_initial_name = 0

        for object_content in objects_to_merge[CONTENTS]:
            object_name = self.__extract_object_name_from_key(object_content[KEY])
            object_to_merge_key = f'{self.__objects_to_merge_prefix}{object_name}'

            if object_name.startswith(self.__objects_to_merge_initial_name):
                total_objects_to_merge_with_initial_name += 1

                if object_name.endswith(new_object_extension):
                    object_to_merge = self.__client.get_object(Bucket=self.__bucket_name, Key=object_to_merge_key)
                    new_object = self.__merge_objects_line_by_line(object_to_merge, new_object)
                self.__client.delete_object(Bucket=self.__bucket_name, Key=object_to_merge_key)

        if not total_objects_to_merge_with_initial_name:
            raise ObjectNotFoundException(f'Objects to merge not found with the initial name '
                                          f'"{self.__objects_to_merge_initial_name}"!')

        return new_object

    @staticmethod
    def __extract_object_name_from_key(object_key: str) -> str:
        return object_key.split(OBJECTS_SEPARATOR)[-1]

    @staticmethod
    def __merge_objects_line_by_line(object_to_merge: dict, new_object: str) -> str:
        for object_line_to_merge in object_to_merge[BODY].iter_lines():
            line_to_merge = object_line_to_merge.decode()
            new_object += f'{line_to_merge}{LINE_BREAK}'

        return new_object

    def __upload_object_to_bucket(self, new_object: str):
        with BytesIO(new_object.encode()) as file_obj:
            self.__client.upload_fileobj(Bucket=self.__bucket_name, Key=f'{self.__new_object_key}', Fileobj=file_obj)

    def __delete_success_objects(self):
        success_objects = [SUCCESS_NO_EXTENSION, SUCCESS_WITH_CRC_EXTENSION]
        for obj in success_objects:
            self.__client.delete_object(Bucket=self.__bucket_name, Key=f'{self.__objects_to_merge_prefix}{obj}')


class BucketNotFoundException(Exception):
    def __init__(self):
        super().__init__('Bucket not found!')


class ObjectNotFoundException(Exception):
    pass
