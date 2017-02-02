#!/usr/bin/env python
"""Test the flow archive."""

import os


import mock

from grr.gui import api_call_handler_utils
from grr.gui import api_call_router_with_approval_checks
from grr.gui import gui_test_lib
from grr.gui import runtests_test
from grr.gui.api_plugins import flow as api_flow

from grr.lib import action_mocks
from grr.lib import aff4
from grr.lib import flags
from grr.lib import flow
from grr.lib import test_lib
from grr.lib import utils
from grr.lib.flows.general import transfer as flows_transfer
from grr.lib.rdfvalues import client as rdf_client
from grr.lib.rdfvalues import paths as rdf_paths


class TestFlowArchive(gui_test_lib.GRRSeleniumTest):

  def setUp(self):
    super(TestFlowArchive, self).setUp()

    with self.ACLChecksDisabled():
      self.client_id = rdf_client.ClientURN("C.0000000000000001")
      with aff4.FACTORY.Open(
          self.client_id, mode="rw", token=self.token) as client:
        client.Set(client.Schema.HOSTNAME("HostC.0000000000000001"))
      self.RequestAndGrantClientApproval(self.client_id)
      self.action_mock = action_mocks.FileFinderClientMock()

  def testDoesNotShowGenerateArchiveButtonForNonExportableRDFValues(self):
    with self.ACLChecksDisabled():
      for _ in test_lib.TestFlowHelper(
          "FlowWithOneNetworkConnectionResult",
          self.action_mock,
          client_id=self.client_id,
          token=self.token):
        pass

    self.Open("/#c=C.0000000000000001")
    self.Click("css=a[grrtarget='client.flows']")
    self.Click("css=td:contains('FlowWithOneNetworkConnectionResult')")
    self.Click("link=Results")

    self.WaitUntil(self.IsTextPresent, "42")
    self.WaitUntilNot(self.IsTextPresent,
                      "Files referenced in this collection can be downloaded")

  def testDoesNotShowGenerateArchiveButtonWhenResultsCollectionIsEmpty(self):
    with self.ACLChecksDisabled():
      for _ in test_lib.TestFlowHelper(
          gui_test_lib.RecursiveTestFlow.__name__,
          self.action_mock,
          client_id=self.client_id,
          token=self.token):
        pass

    self.Open("/#c=C.0000000000000001")
    self.Click("css=a[grrtarget='client.flows']")
    self.Click("css=td:contains('RecursiveTestFlow')")
    self.Click("link=Results")

    self.WaitUntil(self.IsTextPresent, "Value")
    self.WaitUntilNot(self.IsTextPresent,
                      "Files referenced in this collection can be downloaded")

  def testShowsGenerateArchiveButtonForGetFileFlow(self):
    pathspec = rdf_paths.PathSpec(
        path=os.path.join(self.base_path, "test.plist"),
        pathtype=rdf_paths.PathSpec.PathType.OS)
    with self.ACLChecksDisabled():
      for _ in test_lib.TestFlowHelper(
          flows_transfer.GetFile.__name__,
          self.action_mock,
          client_id=self.client_id,
          pathspec=pathspec,
          token=self.token):
        pass

    self.Open("/#c=C.0000000000000001")
    self.Click("css=a[grrtarget='client.flows']")
    self.Click("css=td:contains('GetFile')")
    self.Click("link=Results")

    self.WaitUntil(self.IsTextPresent,
                   "Files referenced in this collection can be downloaded")

  def testGenerateArchiveButtonGetsDisabledAfterClick(self):
    pathspec = rdf_paths.PathSpec(
        path=os.path.join(self.base_path, "test.plist"),
        pathtype=rdf_paths.PathSpec.PathType.OS)
    with self.ACLChecksDisabled():
      for _ in test_lib.TestFlowHelper(
          flows_transfer.GetFile.__name__,
          self.action_mock,
          client_id=self.client_id,
          pathspec=pathspec,
          token=self.token):
        pass

    self.Open("/#c=C.0000000000000001")
    self.Click("css=a[grrtarget='client.flows']")
    self.Click("css=td:contains('GetFile')")
    self.Click("link=Results")
    self.Click("css=button.DownloadButton")

    self.WaitUntil(self.IsElementPresent, "css=button.DownloadButton[disabled]")
    self.WaitUntil(self.IsTextPresent, "Generation has started")

  def testShowsErrorMessageIfArchiveStreamingFailsBeforeFirstChunkIsSent(self):
    pathspec = rdf_paths.PathSpec(
        path=os.path.join(self.base_path, "test.plist"),
        pathtype=rdf_paths.PathSpec.PathType.OS)
    flow_urn = flow.GRRFlow.StartFlow(
        flow_name=flows_transfer.GetFile.__name__,
        client_id=self.client_id,
        pathspec=pathspec,
        token=self.token)

    with self.ACLChecksDisabled():
      for _ in test_lib.TestFlowHelper(
          flow_urn,
          self.action_mock,
          client_id=self.client_id,
          token=self.token):
        pass

    def RaisingStub(*unused_args, **unused_kwargs):
      raise RuntimeError("something went wrong")

    with utils.Stubber(api_call_handler_utils.CollectionArchiveGenerator,
                       "Generate", RaisingStub):
      self.Open("/#c=C.0000000000000001")

      self.Click("css=a[grrtarget='client.flows']")
      self.Click("css=td:contains('GetFile')")
      self.Click("link=Results")
      self.Click("css=button.DownloadButton")
      self.WaitUntil(self.IsTextPresent,
                     "Can't generate archive: Unknown error")
      self.WaitUntil(self.IsUserNotificationPresent,
                     "Archive generation failed for flow %s" %
                     flow_urn.Basename())

  @mock.patch.object(api_call_router_with_approval_checks.
                     ApiCallRouterWithApprovalChecksWithRobotAccess,
                     "GetExportedFlowResults")
  def testClickingOnDownloadAsCsvZipStartsDownload(self, mock_method):
    pathspec = rdf_paths.PathSpec(
        path=os.path.join(self.base_path, "test.plist"),
        pathtype=rdf_paths.PathSpec.PathType.OS)
    with self.ACLChecksDisabled():
      flow_urn = flow.GRRFlow.StartFlow(
          flow_name=flows_transfer.GetFile.__name__,
          client_id=self.client_id,
          pathspec=pathspec,
          token=self.token)
      for _ in test_lib.TestFlowHelper(
          flow_urn,
          self.action_mock,
          client_id=self.client_id,
          token=self.token):
        pass

    self.Open("/#/clients/C.0000000000000001/flows/%s" % flow_urn.Basename())
    self.Click("link=Results")

    self.Click("css=grr-download-collection-as button[name='csv-zip']")

    def MockMethodIsCalled():
      try:
        mock_method.assert_called_once_with(
            api_flow.ApiGetExportedFlowResultsArgs(
                client_id=self.client_id.Basename(),
                flow_id=flow_urn.Basename(),
                plugin_name="csv-zip"),
            token=mock.ANY)

        return True
      except AssertionError:
        return False

    self.WaitUntil(MockMethodIsCalled)

  def testDoesNotShowDownloadAsPanelIfCollectionIsEmpty(self):
    with self.ACLChecksDisabled():
      flow_urn = flow.GRRFlow.StartFlow(
          flow_name=gui_test_lib.RecursiveTestFlow.__name__,
          client_id=self.client_id,
          token=self.token)
      for _ in test_lib.TestFlowHelper(
          flow_urn,
          self.action_mock,
          client_id=self.client_id,
          token=self.token):
        pass

    self.Open("/#/clients/C.0000000000000001/flows/%s" % flow_urn.Basename())
    self.Click("link=Results")

    self.WaitUntil(self.IsTextPresent, "Value")
    self.WaitUntilNot(self.IsElementPresent, "grr-download-collection-as")


def main(argv):
  # Run the full test suite
  runtests_test.SeleniumTestProgram(argv=argv)


if __name__ == "__main__":
  flags.StartMain(main)