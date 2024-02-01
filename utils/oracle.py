from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
import json
import oci
import os

from dotenv import load_dotenv
load_dotenv()


class OracleInstancePrep:
	def __init__(self):
		self.oracle_config = {
			"user": os.getenv('OCI_USER'),
			"key_file": os.getenv('OCI_KEY_FILE'),
			"fingerprint": os.getenv('OCI_FINGERPRINT'),
			"tenancy": os.getenv('OCI_TENANCY'),
			"region": os.getenv('OCI_REGION'),
		}
		self.compute_client = oci.core.ComputeClient(self.oracle_config)

		if not os.path.exists('./config.json'):
			self.INSTANCE_NAME = os.getenv("INSTANCE_NAME")
			if not self.INSTANCE_NAME.strip(): self.INSTANCE_NAME = "ORACLE-VPS"

			self.VCN_NAME = os.getenv("VCN_NAME")
			if not self.VCN_NAME.strip(): self.VCN_NAME = "ORACLE-VCN"

			self.SUBNET_NAME = os.getenv("SUBNET_NAME")
			if not self.SUBNET_NAME.strip(): self.SUBNET_NAME = "ORACLE-SUBNET"

			self.GATEWAY_NAME = os.getenv("GATEWAY_NAME")
			if not self.GATEWAY_NAME.strip(): self.GATEWAY_NAME = "ORACLE-GW"

			self.VNIC_NAME = os.getenv("VNIC_NAME")
			if not self.VNIC_NAME.strip(): self.VNIC_NAME = "ORACLE-VPS-VNIC"


			self.compartment_id = self.oracle_config['tenancy']
			self.network_client = oci.core.VirtualNetworkClient(self.oracle_config)
			self.identity_client = oci.identity.IdentityClient(self.oracle_config)

			print("Getting information for the instance...")
			self.av_domain = self.get_av_domain()
			self.image_id = self.get_image()

			print("Creating necessary resources for the instance...")
			self.vcn_id = self.make_vcn()
			self.subnet_id = self.make_subnet()
			self.gateway_id = self.make_gateway()

			print("Resources created successfully.")

			self.public_key = self.gen_keypair()

			# save all needed details for the instance to config.json so that it can be used later
			with open('./config.json', 'w') as f:
				f.write(f'{{"vcn_id": "{self.vcn_id}", "subnet_id": "{self.subnet_id}", "gateway_id": "{self.gateway_id}", "public_key": "{self.public_key}", "image_id": "{self.image_id}", "av_domain": "{self.av_domain}", "compartment_id": "{self.compartment_id}", "name": "{self.INSTANCE_NAME}"}}, "vnic_name": "{self.VNIC_NAME}"')
		else:
			print("Recovering instance details from config.json...")
			with open('./config.json', 'r') as f:
				config = json.load(f)
				self.vcn_id = config['vcn_id']
				self.subnet_id = config['subnet_id']
				self.gateway_id = config['gateway_id']
				self.public_key = config['public_key']
				self.image_id = config['image_id']
				self.av_domain = config['av_domain']
				self.compartment_id = config['compartment_id']
				self.INSTANCE_NAME = config['name']
				self.VNIC_NAME = config['vnic_name']

			print("Instance details recovered successfully.")


		print("Compiling Launch Instance Details...")
		self.instance_details = oci.core.models.LaunchInstanceDetails(
			compartment_id = self.compartment_id,
			display_name = self.INSTANCE_NAME,
			shape = 'VM.Standard.A1.Flex', # This represents the ARM64 shape
			shape_config = oci.core.models.LaunchInstanceShapeConfigDetails(
				ocpus=4,
				memory_in_gbs=24
			),
			image_id = self.image_id,
			subnet_id = self.subnet_id,
			metadata = {
				"ssh_authorized_keys": self.public_key
			},
			is_pv_encryption_in_transit_enabled = True,
			availability_domain = self.av_domain,
			create_vnic_details = oci.core.models.CreateVnicDetails(
				subnet_id = self.subnet_id,
				assign_public_ip = True,
				assign_private_dns_record = True,
				assign_ipv6_ip = False,
				display_name = self.VNIC_NAME
			)
		)


	def make_vcn(self) -> str: #* Output: VCN ID (result.id)
		print("Creating a VCN...")
		result = self.network_client.create_vcn(
			oci.core.models.CreateVcnDetails(
				cidr_block = '10.10.10.0/24',
				display_name = self.VCN_NAME,
				compartment_id = self.compartment_id
			)
		)

		v_response = oci.wait_until(
			self.network_client,
			self.network_client.get_vcn(result.data.id),
			'lifecycle_state',
			'AVAILABLE'
		)

		print(f"Created a VCN with ID: {v_response.data.id} and name: {self.VCN_NAME}")
		return v_response.data.id


	def make_subnet(self) -> str: #* Output: Subnet ID (result.id)
		print("Creating a subnet...")
		result = self.network_client.create_subnet(
        oci.core.models.CreateSubnetDetails(
				compartment_id = self.compartment_id,
				availability_domain = self.av_domain if self.av_domain else self.get_av_domain(),
				display_name = self.SUBNET_NAME,
				vcn_id = self.vcn_id,
				cidr_block = '10.10.10.0/24'
			)
		)

		s_response = oci.wait_until(
			self.network_client,
			self.network_client.get_subnet(result.data.id),
			'lifecycle_state',
			'AVAILABLE'
		)

		print(f"Created a subnet with ID: {s_response.data.id} and name: {self.SUBNET_NAME}")
		return s_response.data.id


	def make_gateway(self) -> str: #* Output: Gateway ID (result.data.id)
		print("Creating an internet gateway...")
		result = self.network_client.create_internet_gateway(
				oci.core.models.CreateInternetGatewayDetails(
					display_name = self.GATEWAY_NAME,
					compartment_id = self.compartment_id,
					is_enabled=True,
					vcn_id = self.vcn_id
				)
			)

		gw_response = oci.wait_until(
			self.network_client,
			self.network_client.get_internet_gateway(result.data.id),
			'lifecycle_state',
			'AVAILABLE'
		)

		print(f"Created internet gateway: {gw_response.data.id} with name: {self.GATEWAY_NAME}")
		return gw_response.data.id


	def get_av_domain(self) -> str: #* Output: Availability Domain Name (result.name)
		print("Getting availability domains...")
		result = self.identity_client.list_availability_domains(self.compartment_id).data

		if len(result) > 1:
			print("Multiple availability domains found. Please choose one from the list:")
			counter = 0
			for result in result:
				counter += 1
				print(f"{counter}. {result.name}")

			try:
				choice = int(input("Enter the number of the availability domain you want to use: "))
			except:
				print("Invalid choice. Please try again.")
				self.get_av_domain()

			if choice > counter:
				print("Invalid choice. Please try again.")
				self.get_av_domain()

			print(f"Availability domain {result[choice - 1].name} chosen.")
			return result[choice - 1].name
		else:
			print(f"Found only one availability domain ({result[0].name}), chosen.")
			return result[0].name


	def get_image(self) -> str: #* Output: Image ID (latest_aarch64_image.id)
		print("Getting latest Ubuntu 22.04 aarch64 image...")
		images = self.compute_client.list_images(self.compartment_id, operating_system = "Canonical Ubuntu", operating_system_version = "22.04").data

		aarch64_images = [image for image in images if "aarch64" in image.display_name]

		latest_aarch64_image = sorted(aarch64_images, key = lambda image: image.display_name.split("-")[-1], reverse = True)[0]

		print("Obtained Latest Ubuntu 22.04 aarch64 image:", latest_aarch64_image.display_name)
		return latest_aarch64_image.id


	def gen_keypair(self) -> str: #* Output: Public Key (public_key)
		print("Generating SSH keypair...")
		private_key = rsa.generate_private_key(
			backend=default_backend(),
			public_exponent=65537,
			key_size=2048
		)

		pem = private_key.private_bytes(
			encoding=serialization.Encoding.PEM,
			format=serialization.PrivateFormat.PKCS8,
			encryption_algorithm=serialization.NoEncryption()
		)

		with open('./keys/vps_private_key.pem', 'wb') as f:
			f.write(pem)

		public_key = private_key.public_key().public_bytes(
			serialization.Encoding.OpenSSH,
			serialization.PublicFormat.OpenSSH
		)

		with open('./keys/vps_public_key.pub', 'wb') as f:
			f.write(public_key)

		print("Keypair generated successfully and saved to ./keys/ as vps_private_key.pem and vps_public_key.pub")
		return public_key.decode('utf-8')


	def create_instance(self):
		result = self.compute_client.launch_instance(self.instance_details)

		print(result.data)


	def __repr__(self): #* Defines the class's representation as the instance_details
		return self.instance_details